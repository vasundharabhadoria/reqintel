import asyncio
import json
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from groq import (
    APIConnectionError,
    APIStatusError,
    BadRequestError,
    Groq,
    RateLimitError,
)
from pydantic import BaseModel, Field


load_dotenv(override=True)


MODEL_NAME = "openai/gpt-oss-20b"

MAX_RETRIES = 5
MAX_COMPLETION_TOKENS = 2048

MAX_RESOLUTION_ATTEMPTS = 3

# ---------------------------------------------------------------------
# Groq token budgeting
#
# Groq's free tier allows 8,000 tokens per minute for gpt-oss-20b, and a
# request is checked against  prompt tokens + max_completion_tokens.
# One request above the limit is rejected (HTTP 413), and several
# smaller requests inside the same minute are rejected (HTTP 429).
#
# Set GROQ_TPM_LIMIT in .env if your plan has a different limit
# (for example 250000 on the Developer plan).
# ---------------------------------------------------------------------
GROQ_TPM_LIMIT = int(os.getenv("GROQ_TPM_LIMIT", "8000"))
GROQ_TPM_BUDGET = int(GROQ_TPM_LIMIT * 0.9)

MAIN_MAX_COMPLETION_TOKENS = 1500
RESOLUTION_MAX_COMPLETION_TOKENS = 1200

# Largest prompt we ever build. Keeps  prompt + completion  well inside
# the per-minute limit.
MAX_PROMPT_TOKENS = max(
    1500,
    min(4000, GROQ_TPM_BUDGET - MAIN_MAX_COMPLETION_TOKENS - 300),
)

# Progressive trimming levels for the data blocks of a prompt.
_CONTEXT_LEVELS = [
    {"text": 240, "rules_per_category": 12, "matched": 6, "extras": True, "check_phrases": 40},
    {"text": 160, "rules_per_category": 8, "matched": 4, "extras": True, "check_phrases": 30},
    {"text": 100, "rules_per_category": 5, "matched": 3, "extras": False, "check_phrases": 24},
    {"text": 60, "rules_per_category": 3, "matched": 2, "extras": False, "check_phrases": 18},
    # Last resort: the matched rules inside the failed findings are
    # still sent, only the sibling rules of the category are dropped.
    {"text": 60, "rules_per_category": 0, "matched": 2, "extras": False, "check_phrases": 12},
]


def is_blocking_finding(finding: dict[str, Any]) -> bool:
    """
    A finding blocks a requirement from being "clean" when it failed and
    is either:
      - a failed Check category (required information is missing), or
      - a High-severity Issue finding.

    Medium / Low Issue findings stay visible but do not block approval.
    A finding whose evaluation mode is unknown is treated as blocking.
    A waived finding never blocks.
    """

    if finding.get("passed") is True or finding.get("waived") is True:
        return False

    mode = str(finding.get("evaluation_mode") or "").strip().lower()

    if mode == "check" or not mode:
        return True

    return str(finding.get("severity") or "").strip().lower() == "high"


class _TokenPacer:
    """
    Process-wide sliding-window limiter for Groq tokens per minute.

    Requests wait here BEFORE being sent, so retries are not burned on
    429 responses. Real usage replaces the estimate after each call.
    """

    def __init__(self, budget: int, window: float = 60.0) -> None:
        self.budget = budget
        self.window = window
        self._entries: list[list[float]] = []
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self, tokens: int) -> list[float]:
        tokens = max(1, min(int(tokens), self.budget))

        while True:
            async with self._get_lock():
                now = time.monotonic()
                self._entries = [
                    entry
                    for entry in self._entries
                    if now - entry[0] < self.window
                ]
                used = sum(entry[1] for entry in self._entries)

                if not self._entries or used + tokens <= self.budget:
                    entry = [now, float(tokens)]
                    self._entries.append(entry)
                    return entry

                wait = self.window - (now - self._entries[0][0]) + 0.25

            wait = min(max(wait, 0.25), 30.0)
            print(
                f"[AI ANALYSIS] Waiting {wait:.1f}s to stay inside the "
                f"Groq token-per-minute budget."
            )
            await asyncio.sleep(wait)

    @staticmethod
    def settle(entry: list[float], actual_tokens: int | None) -> None:
        if actual_tokens is not None and actual_tokens >= 0:
            entry[1] = float(actual_tokens)


_PACER = _TokenPacer(GROQ_TPM_BUDGET)


ALLOWED_SUGGESTION_TYPES = {
    "missing_requirement",
    "clarity_improvement",
    "completeness_improvement",
    "consistency_fix",
    "other",
}


QUALITY_LABELS = {
    "Good",
    "Needs improvement",
    "Poor",
}


class AISuggestion(BaseModel):
    suggestion_text: str = Field(min_length=1)
    suggestion_type: str = "other"
    resolved_requirement_text: str = Field(min_length=1)


class AIQualityAssessment(BaseModel):
    clarity: str
    completeness: str
    unambiguity: str
    consistency: str
    specificity: str
    testability: str


class AIAnalysisResult(BaseModel):
    analysis_summary: str
    ambiguity_detected: bool = False
    issues: list[str] = Field(default_factory=list)
    suggestions: list[AISuggestion] = Field(default_factory=list)
    quality_assessment: AIQualityAssessment


class AIResolutionResult(BaseModel):
    resolved_requirement_text: str = Field(min_length=1)
    unresolved_checks: list[str] = Field(default_factory=list)


class AIAnalysisService:
    def __init__(self):
        # The client is created lazily so that endpoints which never call
        # the AI (list requirements, versions, ...) do not fail when the
        # key is missing.
        self._client: Groq | None = None

    @property
    def client(self) -> Groq:
        if self._client is None:
            api_key = os.getenv("GROQ_AI_API_KEY")

            if not api_key:
                raise ValueError(
                    "GROQ_AI_API_KEY is not configured in .env"
                )

            self._client = Groq(api_key=api_key)

        return self._client

    def _compact_findings(
        self,
        findings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Preserve the Rule Engine findings needed by the AI.

        The Rule Engine remains the source of truth.

        In addition to the category-level finding, preserve the
        ACTUALLY MATCHED Master Module rules returned by the Rule Engine.
        This is important because a category can contain several rules,
        while only some of them may have matched the current requirement.
        """

        compact = []

        for finding in findings:
            matched_rules = []

            for rule in finding.get("rules") or []:
                matched_rules.append(
                    {
                        "rule": str(
                            rule.get("rule")
                            or rule.get("rule_name")
                            or ""
                        )[:400],
                        "rule_type": rule.get("rule_type"),
                        "severity": rule.get("severity"),
                        "description": str(
                            rule.get("description") or ""
                        )[:400],
                        "why_it_matters": str(
                            rule.get("why_it_matters") or ""
                        )[:400],
                        "recommendation": str(
                            rule.get("recommendation") or ""
                        )[:400],
                    }
                )

            compact.append(
                {
                    "rule_name": finding.get("rule_name"),
                    "category": finding.get("category")
                    or finding.get("category_name"),
                    "passed": finding.get("passed") is True,
                    "severity": finding.get("severity"),
                    "message": str(
                        finding.get("message")
                        or finding.get("description")
                        or ""
                    )[:500],
                    "recommendation": str(
                        finding.get("recommendation") or ""
                    )[:500],
                    "evaluation_mode": finding.get("evaluation_mode"),
                    "actually_matched_rules": matched_rules,
                }
            )

        return compact

    def _compact_master_rules(
        self,
        rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Preserve Master Module rules supplied by the service.
        """

        compact = []

        for rule in rules:
            compact.append(
                {
                    "category": rule.get("category")
                    or rule.get("category_name"),
                    "category_description": str(
                        rule.get("category_description") or ""
                    )[:400],
                    "rule": str(
                        rule.get("rule") or ""
                    )[:400],
                    "description": str(
                        rule.get("description") or ""
                    )[:400],
                    "why_it_matters": str(
                        rule.get("why_it_matters") or ""
                    )[:400],
                    "severity": rule.get("severity"),
                    "recommendation": str(
                        rule.get("recommendation") or ""
                    )[:400],
                    "rule_type": rule.get("rule_type"),
                    "evaluation_mode": rule.get("evaluation_mode"),
                }
            )

        return compact

    def _compact_relevant_master_rules(
        self,
        rules: list[dict[str, Any]],
        failed_findings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Only send Master Module rules relevant to failed checks.

        This keeps the Groq request smaller while retaining the actual
        engineering rules responsible for the failures.
        """

        if not failed_findings:
            return []

        failed_categories = {
            str(
                finding.get("category")
                or finding.get("category_name")
                or ""
            )
            .strip()
            .lower()
            for finding in failed_findings
            if (
                finding.get("category")
                or finding.get("category_name")
            )
        }

        failed_rule_names = {
            str(
                finding.get("rule_name")
                or finding.get("rule")
                or ""
            )
            .strip()
            .lower()
            for finding in failed_findings
            if (
                finding.get("rule_name")
                or finding.get("rule")
            )
        }

        relevant = []

        for rule in rules:
            category = str(
                rule.get("category")
                or rule.get("category_name")
                or ""
            ).strip()

            rule_name = str(
                rule.get("rule")
                or rule.get("rule_name")
                or ""
            ).strip()

            category_key = category.lower()
            rule_key = rule_name.lower()

            if (
                rule_key in failed_rule_names
                or (
                    category_key
                    and category_key in failed_categories
                )
            ):
                relevant.append(rule)

        return self._compact_master_rules(relevant)

    # ---------------------------------------------------------------
    # Prompt size control
    # ---------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        # JSON-heavy English text is roughly 3 characters per token.
        # This intentionally over-estimates a little.
        return max(1, len(text) // 3)

    @staticmethod
    def _dumps(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )

    @staticmethod
    def _clip(value: Any, limit: int) -> str:
        text = " ".join(str(value or "").split())

        if len(text) <= limit:
            return text

        return text[: max(0, limit - 3)].rstrip() + "..."

    @staticmethod
    def _category_of(finding: dict[str, Any]) -> str:
        return str(
            finding.get("category")
            or finding.get("category_name")
            or ""
        ).strip()

    @staticmethod
    def _drop_empty(data: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in data.items()
            if value not in (None, "", [], {})
        }

    def _compact_finding(
        self,
        finding: dict[str, Any],
        level: dict[str, Any],
        passed: bool,
    ) -> dict[str, Any]:
        """
        Compact one Rule Engine finding.

        Failed findings keep the exact matched rules (the primary
        evidence for the AI). Passed findings only keep the NAMES of the
        rules that satisfy them, so the AI can preserve them.
        """

        text_limit = level["text"]
        matched: list[Any] = []
        seen: set[str] = set()

        for rule in finding.get("rules") or []:
            name = self._clip(
                rule.get("rule") or rule.get("rule_name"),
                text_limit if not passed else 60,
            )
            key = name.lower()

            if not name or key in seen:
                continue

            seen.add(key)

            if passed:
                matched.append(name)
            else:
                item = {
                    "rule": name,
                    "rule_type": rule.get("rule_type"),
                    "recommendation": self._clip(
                        rule.get("recommendation"), text_limit
                    ),
                }

                if level["extras"]:
                    item["why_it_matters"] = self._clip(
                        rule.get("why_it_matters"), text_limit
                    )

                matched.append(self._drop_empty(item))

            if len(matched) >= (3 if passed else level["matched"]):
                break

        category = self._category_of(finding)
        rule_name = str(finding.get("rule_name") or "").strip()

        if passed:
            return self._drop_empty(
                {
                    "category": category or rule_name,
                    "evaluation_mode": finding.get("evaluation_mode"),
                    "satisfied_by": matched,
                }
            )

        return self._drop_empty(
            {
                "category": category or rule_name,
                "rule_name": (
                    rule_name
                    if rule_name and rule_name != category
                    else None
                ),
                "evaluation_mode": finding.get("evaluation_mode"),
                "severity": finding.get("severity"),
                "message": self._clip(
                    finding.get("message")
                    or finding.get("description"),
                    text_limit * 2,
                ),
                "recommendation": self._clip(
                    finding.get("recommendation"), text_limit
                ),
                "actually_matched_rules": matched,
            }
        )

    def _select_relevant_rules(
        self,
        master_rules: list[dict[str, Any]],
        failed_findings: list[dict[str, Any]],
        level: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Master rules of the FAILED categories only, capped per category.

        Rules that already appear under "actually_matched_rules" are not
        repeated. Passed categories never need their rules sent.
        """

        failed_categories = {
            self._category_of(finding).lower()
            for finding in failed_findings
            if self._category_of(finding)
        }

        if not failed_categories:
            return []

        matched_keys: set[tuple[str, str]] = set()

        for finding in failed_findings:
            category = self._category_of(finding).lower()

            for rule in finding.get("rules") or []:
                matched_keys.add(
                    (
                        category,
                        str(
                            rule.get("rule")
                            or rule.get("rule_name")
                            or ""
                        ).strip().lower(),
                    )
                )

        per_category: dict[str, list[dict[str, Any]]] = {}
        seen: set[tuple[str, str]] = set()

        # Check categories are satisfied by INCLUDING one of their
        # phrases, so the AI needs the full phrase list (names only).
        check_categories = {
            str(
                rule.get("category") or rule.get("category_name") or ""
            ).strip().lower()
            for rule in master_rules
            if str(rule.get("evaluation_mode") or "").strip().lower()
            == "check"
        }
        check_groups: dict[str, list[str]] = {}

        for rule in master_rules:
            category = str(
                rule.get("category")
                or rule.get("category_name")
                or ""
            ).strip()
            category_key = category.lower()
            rule_name = str(rule.get("rule") or "").strip()
            key = (category_key, rule_name.lower())

            if (
                category_key not in failed_categories
                or not rule_name
                or key in seen
                or key in matched_keys
            ):
                continue

            seen.add(key)

            if category_key in check_categories:
                phrases = check_groups.setdefault(category, [])

                if len(phrases) < level["check_phrases"]:
                    phrases.append(self._clip(rule_name, 60))

                continue

            bucket = per_category.setdefault(category, [])

            if len(bucket) >= level["rules_per_category"]:
                continue

            item = {
                "category": category,
                "rule": self._clip(rule_name, level["text"]),
                "rule_type": rule.get("rule_type"),
                "evaluation_mode": rule.get("evaluation_mode"),
                "description": self._clip(
                    rule.get("description"), level["text"]
                ),
                "recommendation": self._clip(
                    rule.get("recommendation"), level["text"]
                ),
            }

            if level["extras"]:
                item["why_it_matters"] = self._clip(
                    rule.get("why_it_matters"), level["text"]
                )

            bucket.append(self._drop_empty(item))

        selected = [
            rule
            for bucket in per_category.values()
            for rule in bucket
        ]

        for category, phrases in check_groups.items():
            selected.append(
                {
                    "category": category,
                    "evaluation_mode": "Check",
                    "include_at_least_one_of": phrases,
                }
            )

        return selected

    def _build_prompt_context(
        self,
        rule_findings: list[dict[str, Any]],
        master_rules: list[dict[str, Any]],
        max_tokens: int,
        include_passed: bool = True,
    ) -> dict[str, str]:
        """
        Build the data blocks of a prompt and trim them until they fit
        inside max_tokens.
        """

        failed = [
            finding
            for finding in rule_findings
            if finding.get("passed") is not True
        ]
        passed = [
            finding
            for finding in rule_findings
            if finding.get("passed") is True
        ]

        findings_json = rules_json = ""

        for index, level in enumerate(_CONTEXT_LEVELS):
            failed_compact = [
                self._compact_finding(finding, level, passed=False)
                for finding in failed
            ]

            if include_passed:
                findings_json = self._dumps(
                    {
                        "failed": failed_compact,
                        "passed": [
                            self._compact_finding(
                                finding, level, passed=True
                            )
                            for finding in passed
                        ],
                    }
                )
            else:
                findings_json = self._dumps(failed_compact)

            rules_json = self._dumps(
                self._select_relevant_rules(
                    master_rules, failed, level
                )
            )

            used = (
                self._estimate_tokens(findings_json)
                + self._estimate_tokens(rules_json)
            )

            if used <= max_tokens:
                break

            if index == len(_CONTEXT_LEVELS) - 1:
                print(
                    "[AI ANALYSIS] Context still ~"
                    f"{used} tokens after maximum trimming."
                )

        return {
            "findings_json": findings_json,
            "rules_json": rules_json,
        }

    # ---------------------------------------------------------------
    # Groq call with pacing, retries and structured-output recovery
    # ---------------------------------------------------------------

    def _estimate_request_tokens(
        self,
        request_kwargs: dict[str, Any],
    ) -> int:
        prompt_chars = sum(
            len(str(message.get("content") or ""))
            for message in request_kwargs.get("messages", [])
        )

        return (
            prompt_chars // 3
            + int(
                request_kwargs.get(
                    "max_completion_tokens",
                    MAX_COMPLETION_TOKENS,
                )
            )
        )

    def _fit_completion_tokens(
        self,
        request_kwargs: dict[str, Any],
    ) -> None:
        """
        Lower max_completion_tokens when prompt + completion would
        exceed the per-minute limit (HTTP 413 otherwise).
        """

        prompt_tokens = self._estimate_request_tokens(
            {**request_kwargs, "max_completion_tokens": 0}
        )
        room = GROQ_TPM_LIMIT - prompt_tokens - 200

        if room < 400:
            raise RuntimeError(
                "The AI prompt is too large for the Groq token limit "
                f"(~{prompt_tokens} tokens, limit {GROQ_TPM_LIMIT}). "
                "Reduce the requirement text or the number of master "
                "rules, or upgrade the Groq plan."
            )

        current = int(
            request_kwargs.get(
                "max_completion_tokens", MAX_COMPLETION_TOKENS
            )
        )

        if current > room:
            request_kwargs["max_completion_tokens"] = room

    def _raise_completion_tokens(
        self,
        request_kwargs: dict[str, Any],
    ) -> bool:
        """
        gpt-oss spends part of max_completion_tokens on hidden
        reasoning. When the answer is cut off or empty, retry with a
        larger ceiling (as far as the per-minute limit allows).
        """

        current = int(
            request_kwargs.get(
                "max_completion_tokens", MAX_COMPLETION_TOKENS
            )
        )
        prompt_tokens = self._estimate_request_tokens(
            {**request_kwargs, "max_completion_tokens": 0}
        )
        ceiling = GROQ_TPM_LIMIT - prompt_tokens - 200
        new_value = min(int(current * 1.5), ceiling)

        if new_value <= current:
            return False

        request_kwargs["max_completion_tokens"] = new_value
        return True

    def _switch_to_json_object(
        self,
        request_kwargs: dict[str, Any],
    ) -> None:
        """
        Fallback when strict json_schema keeps failing. JSON-object mode
        needs the word JSON in the messages and has no schema, so the
        schema is described in a system message.
        """

        schema = (
            (request_kwargs.get("response_format") or {})
            .get("json_schema", {})
            .get("schema")
        )

        instruction = (
            "Respond with ONE valid JSON object only. "
            "No markdown, no commentary."
        )

        if schema:
            instruction += (
                " The object must follow this JSON schema: "
                + self._dumps(schema)
            )

        request_kwargs["response_format"] = {"type": "json_object"}
        request_kwargs["messages"] = [
            {"role": "system", "content": instruction},
            *[
                message
                for message in request_kwargs["messages"]
                if not (
                    message.get("role") == "system"
                    and str(message.get("content", "")).startswith(
                        "Respond with ONE valid JSON object only."
                    )
                )
            ],
        ]

    @staticmethod
    def _salvage_failed_generation(
        exc: Exception,
        request_kwargs: dict[str, Any],
    ) -> str | None:
        """
        Groq returns the rejected text in failed_generation. When it is
        valid JSON that already contains every required top-level key,
        use it instead of paying for another request.

        The SDK exposes the error body either as {"error": {...}} or as
        the inner {...} dict, so both shapes are accepted.
        """

        body = getattr(exc, "body", None)
        error = None

        if isinstance(body, dict):
            inner = body.get("error")
            error = inner if isinstance(inner, dict) else body

        failed = (
            error.get("failed_generation")
            if isinstance(error, dict)
            else None
        )

        if not isinstance(failed, str) or not failed.strip():
            return None

        text = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            failed.strip(),
        )

        try:
            parsed = json.loads(text)
        except ValueError:
            return None

        required = (
            (request_kwargs.get("response_format") or {})
            .get("json_schema", {})
            .get("schema", {})
            .get("required", [])
        )

        if not isinstance(parsed, dict) or any(
            key not in parsed for key in required
        ):
            return None

        return text

    async def _wait_for_rate_limit(
        self,
        error: Exception,
        attempt: int,
    ) -> None:

        message = str(error)

        match = re.search(
            r"try again in\s+(?:(\d+)m)?\s*([0-9]+(?:\.[0-9]+)?)s",
            message,
            re.IGNORECASE,
        )

        if match:
            minutes = float(match.group(1) or 0)
            seconds = float(match.group(2))
            delay = min(minutes * 60 + seconds + 0.5, 60.0)
        else:
            delay = min(
                2.0 * (attempt + 1),
                10.0,
            )

        print(
            f"[AI ANALYSIS] Groq rate limit reached. "
            f"Retrying in {delay:.1f}s "
            f"(attempt {attempt + 1}/{MAX_RETRIES})"
        )

        await asyncio.sleep(delay)

    async def _call_groq(
        self,
        request_kwargs: dict[str, Any],
    ) -> str:

        kwargs = dict(request_kwargs)
        kwargs["messages"] = [
            dict(message) for message in request_kwargs["messages"]
        ]

        last_error: Exception | None = None
        schema_failures = 0

        self._fit_completion_tokens(kwargs)

        for attempt in range(MAX_RETRIES):
            entry = await _PACER.acquire(
                self._estimate_request_tokens(kwargs)
            )

            try:
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    **kwargs,
                )

            except RateLimitError as exc:
                last_error = exc
                message = str(exc).lower()

                if (
                    "tokens per day" in message
                    or "tpd" in message
                ):
                    raise RuntimeError(
                        "Groq daily token limit has been reached. "
                        "Wait for the quota reset before running AI "
                        "Analysis again."
                    ) from exc

                if attempt == MAX_RETRIES - 1:
                    break

                await self._wait_for_rate_limit(exc, attempt)
                continue

            except BadRequestError as exc:
                # A rejected request is not charged against the window.
                _PACER.settle(entry, 0)
                last_error = exc
                message = str(exc).lower()

                if not (
                    "json_validate_failed" in message
                    or "failed to validate json" in message
                    or "does not match the expected schema" in message
                    or "json_schema" in message
                    or "json schema" in message
                ):
                    raise

                salvaged = self._salvage_failed_generation(
                    exc, kwargs
                )

                if salvaged:
                    print(
                        "[AI ANALYSIS] Recovered valid JSON from "
                        "failed_generation."
                    )
                    return salvaged

                schema_failures += 1

                if attempt == MAX_RETRIES - 1 or schema_failures > 2:
                    break

                if schema_failures == 1:
                    # Usually the model ran out of tokens while
                    # reasoning (failed_generation is empty).
                    self._raise_completion_tokens(kwargs)
                    print(
                        "[AI ANALYSIS] Structured output failed. "
                        "Retrying with a larger completion budget "
                        f"({kwargs.get('max_completion_tokens')})."
                    )
                else:
                    print(
                        "[AI ANALYSIS] Structured output failed again. "
                        "Retrying in JSON-object mode."
                    )
                    self._switch_to_json_object(kwargs)

                continue

            except APIStatusError as exc:
                last_error = exc
                status_code = getattr(exc, "status_code", 0) or 0
                message = str(exc).lower()

                if status_code == 413 or "request too large" in message:
                    _PACER.settle(entry, 0)
                    raise RuntimeError(
                        "Groq rejected the request as too large for "
                        "the tokens-per-minute limit "
                        f"(limit {GROQ_TPM_LIMIT}). {exc}"
                    ) from exc

                if status_code >= 500 and attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(min(2.0 * (attempt + 1), 10.0))
                    continue

                raise

            except APIConnectionError as exc:
                last_error = exc

                if attempt == MAX_RETRIES - 1:
                    break

                await asyncio.sleep(min(2.0 * (attempt + 1), 10.0))
                continue

            usage = getattr(response, "usage", None)
            _PACER.settle(entry, getattr(usage, "total_tokens", None))

            choice = response.choices[0]
            content = (choice.message.content or "").strip()
            finish_reason = getattr(choice, "finish_reason", None)

            if not content or finish_reason == "length":
                # Empty or truncated answer: the ceiling was too low.
                if (
                    attempt < MAX_RETRIES - 1
                    and self._raise_completion_tokens(kwargs)
                ):
                    print(
                        "[AI ANALYSIS] Groq response was empty or "
                        "truncated. Retrying with "
                        f"max_completion_tokens="
                        f"{kwargs.get('max_completion_tokens')}."
                    )
                    continue

                raise RuntimeError(
                    "Groq returned an empty or truncated AI response"
                )

            return content

        raise RuntimeError(
            f"Groq request failed after {MAX_RETRIES} attempts: "
            f"{last_error}"
        )

    def _build_main_schema(self) -> dict[str, Any]:

        return {
            "type": "object",
            "properties": {
                "analysis_summary": {
                    "type": "string"
                },
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                },
                "suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "suggestion_text": {
                                "type": "string"
                            },
                            "suggestion_type": {
                                "type": "string"
                            },
                            "resolved_requirement_text": {
                                "type": "string"
                            }
                        },
                        "required": [
                            "suggestion_text",
                            "suggestion_type",
                            "resolved_requirement_text"
                        ],
                        "additionalProperties": False
                    }
                },
                "quality_assessment": {
                    "type": "object",
                    "properties": {
                        "clarity": {
                            "type": "string",
                            "enum": [
                                "Good",
                                "Needs improvement",
                                "Poor"
                            ]
                        },
                        "completeness": {
                            "type": "string",
                            "enum": [
                                "Good",
                                "Needs improvement",
                                "Poor"
                            ]
                        },
                        "unambiguity": {
                            "type": "string",
                            "enum": [
                                "Good",
                                "Needs improvement",
                                "Poor"
                            ]
                        },
                        "consistency": {
                            "type": "string",
                            "enum": [
                                "Good",
                                "Needs improvement",
                                "Poor"
                            ]
                        },
                        "specificity": {
                            "type": "string",
                            "enum": [
                                "Good",
                                "Needs improvement",
                                "Poor"
                            ]
                        },
                        "testability": {
                            "type": "string",
                            "enum": [
                                "Good",
                                "Needs improvement",
                                "Poor"
                            ]
                        }
                    },
                    "required": [
                        "clarity",
                        "completeness",
                        "unambiguity",
                        "consistency",
                        "specificity",
                        "testability"
                    ],
                    "additionalProperties": False
                }
            },
            "required": [
                "analysis_summary",
                "issues",
                "suggestions",
                "quality_assessment"
            ],
            "additionalProperties": False
        }

    def _build_resolution_schema(self) -> dict[str, Any]:

        return {
            "type": "object",
            "properties": {
                "resolved_requirement_text": {
                    "type": "string"
                },
                "unresolved_checks": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                }
            },
            "required": [
                "resolved_requirement_text",
                "unresolved_checks"
            ],
            "additionalProperties": False
        }

    async def _resolve_failed_requirement(
        self,
        original_requirement: str,
        candidate_requirement: str,
        failed_findings: list[dict[str, Any]],
        relevant_master_rules: list[dict[str, Any]],
    ) -> str:
        """
        Resolve a requirement using the ACTUAL Rule Engine.

        The Master Module is dynamic. No category name, rule name, or
        business domain is hardcoded here.

        Every AI-generated candidate is executed through the real Rule
        Engine. Only a candidate with zero actual failed findings is
        accepted as resolved.

        No repository version is created here. This is an internal AI
        validation loop only.
        """

        from services.rule_engine import analyze_requirements

        current_candidate = candidate_requirement

        def run_rule_engine(
            candidate: str,
        ) -> list[dict[str, Any]]:

            results = analyze_requirements(
                [
                    {
                        "id": "__ai_resolution_candidate__",
                        "text": candidate,
                    }
                ]
            )

            if not results:
                raise RuntimeError(
                    "Rule Engine returned no result while validating "
                    "the AI resolved requirement."
                )

            return (
                results[0].get("findings", [])
                or []
            )

        actual_findings = run_rule_engine(
            current_candidate
        )

        actual_failed_findings = [
            finding
            for finding in actual_findings
            if is_blocking_finding(finding)
        ]

        print(
            "[AI ANALYSIS] Initial candidate actual Rule Engine result: "
            f"{len(actual_failed_findings)} failed checks."
        )

        if not actual_failed_findings:
            print(
                "[AI ANALYSIS] Initial candidate passed the actual "
                "Rule Engine."
            )
            return current_candidate

        best_candidate = current_candidate
        best_failed_findings = list(actual_failed_findings)
        best_failure_count = len(actual_failed_findings)

        seen_failure_signatures = set()
        rejected_candidates: list[str] = []
        retry_hint = ""

        def failure_signature(
            findings: list[dict[str, Any]],
        ) -> tuple:
            signature = []

            for finding in findings:
                signature.append(
                    (
                        str(
                            finding.get("category")
                            or finding.get("category_name")
                            or ""
                        ).strip().lower(),
                        str(
                            finding.get("rule_name")
                            or finding.get("rule")
                            or ""
                        ).strip().lower(),
                        str(
                            finding.get("message")
                            or ""
                        ).strip().lower(),
                        finding.get("passed") is True,
                    )
                )

            return tuple(sorted(signature))

        seen_failure_signatures.add(
            failure_signature(actual_failed_findings)
        )

        for resolution_attempt in range(
            MAX_RESOLUTION_ATTEMPTS
        ):

            rejected_json = self._dumps(
                [
                    self._clip(candidate, 600)
                    for candidate in rejected_candidates[-3:]
                ]
            )

            def render_prompt(
                failed_json: str,
                rules_json: str,
            ) -> str:
                return f"""
You are the requirement resolution engine for ReqIntel.

Your task is to revise the CURRENT CANDIDATE REQUIREMENT so that it
passes every FAILED check reported by the ACTUAL Rule Engine.

IMPORTANT:

- The Rule Engine result is authoritative.
- The Master Module is dynamic.
- Categories and rules are configured by an administrator and may be
  added, removed, or changed at any time.
- Never assume a fixed category name or a fixed business domain.
- Never use hardcoded interpretations of category names.
- Use only the actual failed findings and the supplied Master Module
  metadata to determine what must change.

ORIGINAL REQUIREMENT:
{original_requirement[:3000]}

CURRENT CANDIDATE REQUIREMENT:
{current_candidate[:4000]}

ACTUAL FAILED RULE ENGINE FINDINGS:
{failed_json}

ACTUALLY MATCHED MASTER MODULE RULES:
The "actually_matched_rules" field above identifies the exact configured
rules that matched this current candidate. Treat those matches as the
specific reason for the corresponding failed category finding.

HOW TO READ THE RULES BELOW:
- An entry with "include_at_least_one_of" is a CHECK category. The
  requirement passes only if its text contains at least one of those
  exact phrases (case-insensitive, as plain text). Work one of them
  naturally into the sentence.
- Under "actually_matched_rules" are ISSUE rules that matched. Remove or
  rephrase exactly those words/phrases without changing the meaning, and
  do not introduce other listed rule words.

RELEVANT MASTER MODULE RULES FOR THESE CURRENT FAILURES
(rules already listed under actually_matched_rules are not repeated):
{rules_json}

PREVIOUS CANDIDATES REJECTED BECAUSE THEY DID NOT IMPROVE THE ACTUAL
RULE ENGINE RESULT:
{rejected_json}

PREVIOUS BEST FAILURE COUNT:
{best_failure_count}
{retry_hint}

MANDATORY BEHAVIOR:

1. Address EVERY ACTUAL failed Rule Engine check.

2. Preserve the original business intent.

3. Make the smallest meaningful correction that resolves the failures.

4. Do not remove an existing required behavior merely to bypass a rule.

5. Do not invent unsupported facts, actors, values, limits, dates,
   systems, technologies, or business rules.

6. Do not simply repeat the current candidate.

7. If multiple failed checks exist, produce ONE requirement that
   addresses all of them together.

8. The output must be one complete, standalone software requirement.

9. Do not mention Rule Engine, Master Module, categories, rules,
   analysis, or these instructions inside the requirement.

10. The returned requirement will be executed through the ACTUAL Rule
    Engine again.

11. Your own unresolved_checks judgment is NOT authoritative.

12. Try to improve the actual failure count. Do not intentionally
    return a candidate that leaves the same failure state unchanged.

13. If the previous attempt reduced the number of failures, preserve
    those successful corrections while addressing the remaining
    failures.

14. If a new failure appeared because of the previous correction,
    reconsider the wording so that the original intent and previously
    resolved checks are both preserved.

15. Pay special attention to the "actually_matched_rules" field. Those
    are the exact configured rules that caused the current failed
    category. Do not treat an unmatched rule in the same category as
    the reason for the current failure.

16. If a failed category uses evaluation_mode "Issue", a currently
    matched Keyword, Pattern, or Presence rule must be removed from the
    candidate in a way that preserves the requirement's business intent.
    Do not merely replace one forbidden configured trigger with another
    trigger from the same failed category.

17. If the failed category is intended to detect compound requirements,
    rewrite the candidate as one atomic requirement while preserving as
    much of the original business intent as the single-requirement format
    allows. Do not simply replace "and" with "and then", "as well as", or
    another configured compound trigger.

18. A candidate is not successful merely because it is worded
    differently. It is successful only when the ACTUAL Rule Engine
    returns zero failed checks. If the previous candidate was rejected,
    produce materially different wording that addresses the exact
    matched rule.

RULE INTERPRETATION:

The Master Module supplied above defines the actual configured rules.

For each supplied rule:

- category identifies the configured category.
- rule identifies the configured rule value.
- rule_type describes how the rule is evaluated.
- evaluation_mode describes whether a match is desirable.

If evaluation_mode is "Issue", a matching configured rule causes a
failure.

If evaluation_mode is "Check", a matching configured rule satisfies
the check.

Use the supplied description, why_it_matters, and recommendation as
additional context.

Never assume any category-specific behavior that is not present in the
supplied data.

The current Rule Engine may use configured rule types such as:

- Keyword
- Pattern
- Presence

Preserve the business meaning while satisfying the actual configured
rule behavior.

OUTPUT:
Return valid json only.

resolved_requirement_text:
The complete corrected requirement.

unresolved_checks:
A brief informational list of checks you believe may still need
attention.

This field is NOT used to decide whether the candidate passed.

The actual Rule Engine decides whether the candidate passes.
"""

            base_prompt = render_prompt("[]", "[]")
            data_budget = max(
                600,
                MAX_PROMPT_TOKENS
                - self._estimate_tokens(base_prompt),
            )
            context = self._build_prompt_context(
                actual_failed_findings,
                relevant_master_rules,
                data_budget,
                include_passed=False,
            )
            prompt = render_prompt(
                context["findings_json"],
                context["rules_json"],
            )

            print(
                "[AI ANALYSIS] Resolution prompt ~"
                f"{self._estimate_tokens(prompt)} tokens "
                f"(limit {MAX_PROMPT_TOKENS})."
            )

            request_kwargs = {
                "model": MODEL_NAME,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "temperature": 0,
                "max_completion_tokens": RESOLUTION_MAX_COMPLETION_TOKENS,
                "reasoning_effort": "low",
                "include_reasoning": False,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "reqintel_requirement_resolution",
                        "strict": True,
                        "schema": self._build_resolution_schema(),
                    }
                }
            }

            try:
                raw_content = await self._call_groq(
                    request_kwargs
                )

                data = json.loads(raw_content)

                resolved_text = str(
                    data.get(
                        "resolved_requirement_text",
                        ""
                    )
                ).strip()

                if not resolved_text:
                    raise RuntimeError(
                        "AI resolution returned an empty requirement"
                    )

                original_normalized = " ".join(
                    original_requirement.split()
                ).strip().lower()

                resolved_normalized = " ".join(
                    resolved_text.split()
                ).strip().lower()

                current_normalized = " ".join(
                    current_candidate.split()
                ).strip().lower()

                if (
                    resolved_normalized == original_normalized
                    or resolved_normalized == current_normalized
                    or resolved_normalized in {
                        " ".join(candidate.split()).strip().lower()
                        for candidate in rejected_candidates
                    }
                ):
                    rejected_candidates.append(resolved_text)

                    print(
                        "[AI ANALYSIS] AI returned an unchanged or "
                        "previously rejected requirement. Requesting a "
                        "materially different correction."
                    )

                    if resolution_attempt == (
                        MAX_RESOLUTION_ATTEMPTS - 1
                    ):
                        break

                    # Keep the candidate text clean; only the prompt
                    # carries the hint.
                    retry_hint = (
                        "NOTE: The previous answer was rejected because "
                        "it did not change the actual Rule Engine "
                        "failure. Produce a materially different "
                        "correction."
                    )
                    continue

                candidate_findings = run_rule_engine(
                    resolved_text
                )

                candidate_failed_findings = [
                    finding
                    for finding in candidate_findings
                    if is_blocking_finding(finding)
                ]

                candidate_failure_count = len(
                    candidate_failed_findings
                )

                print(
                    f"[AI ANALYSIS] Resolution attempt "
                    f"{resolution_attempt + 1}/"
                    f"{MAX_RESOLUTION_ATTEMPTS}: "
                    f"actual Rule Engine failures = "
                    f"{candidate_failure_count}."
                )

                candidate_signature = failure_signature(
                    candidate_failed_findings
                )

                if not candidate_failed_findings:
                    print(
                        "[AI ANALYSIS] Candidate passed the ACTUAL "
                        "Rule Engine. Resolution complete."
                    )
                    return resolved_text

                if candidate_failure_count < best_failure_count:
                    best_candidate = resolved_text
                    best_failed_findings = list(
                        candidate_failed_findings
                    )
                    best_failure_count = candidate_failure_count

                    print(
                        "[AI ANALYSIS] Candidate improved the failure "
                        f"count from {len(actual_failed_findings)} "
                        f"to {candidate_failure_count}."
                    )

                elif candidate_signature in seen_failure_signatures:
                    print(
                        "[AI ANALYSIS] Candidate produced a previously "
                        "seen failure state. Keeping the best candidate."
                    )

                else:
                    print(
                        "[AI ANALYSIS] Candidate did not reduce the "
                        "failure count. Continuing with the current "
                        "failure state."
                    )

                seen_failure_signatures.add(
                    candidate_signature
                )

                current_candidate = resolved_text
                retry_hint = ""
                actual_findings = candidate_findings
                actual_failed_findings = candidate_failed_findings

                if resolution_attempt < (
                    MAX_RESOLUTION_ATTEMPTS - 1
                ):
                    print(
                        "[AI ANALYSIS] Sending CURRENT actual failures "
                        "to the next resolution attempt."
                    )

            except Exception as exc:
                print(
                    "[AI ANALYSIS] Resolution attempt failed: "
                    f"{exc}"
                )

                if "daily token limit" in str(exc).lower():
                    # Retrying cannot succeed. Keep the best candidate.
                    break

                if resolution_attempt == (
                    MAX_RESOLUTION_ATTEMPTS - 1
                ):
                    break

        remaining_rule_names = [
            str(
                finding.get("rule_name")
                or finding.get("category")
                or "Unknown Rule"
            )
            for finding in best_failed_findings
        ]

        print(
            "[AI ANALYSIS] Internal resolution did not reach zero "
            "Rule Engine failures. Returning the best candidate "
            f"with {best_failure_count} remaining failure(s)."
        )

        print(
            "[AI ANALYSIS] Remaining failed checks: "
            + ", ".join(remaining_rule_names)
        )

        return best_candidate

    async def analyze_requirement(
        self,
        requirement_text: str,
        rule_findings: list[dict[str, Any]] | None = None,
        master_rules: list[dict[str, Any]] | None = None,
        resolve_failed_requirement: bool = False,
    ) -> AIAnalysisResult:

        rule_findings = rule_findings or []
        master_rules = master_rules or []

        failed_rule_findings = [
            finding
            for finding in rule_findings
            if finding.get("passed") is not True
        ]

        def render_prompt(
            findings_json: str,
            rules_json: str,
        ) -> str:
            return f"""
You are ReqIntel, a requirements engineering assistant.

Analyze ONE software requirement for quality.

The Rule Engine is the source of truth.
The Master Module defines the categories and rules used by the Rule Engine.

Do not approve or reject the requirement.
Do not invent facts.

CURRENT REQUIREMENT:
{requirement_text[:3500]}

RULE ENGINE FINDINGS:
{findings_json}

IMPORTANT:
"failed" lists every failed check in full. "passed" lists the checks that
currently pass; "satisfied_by" names the configured rules that make a
passing check pass. Preserve every currently passing check while
correcting all failed checks. For each failed category,
"actually_matched_rules" identifies the exact Master Module rules that
matched the current requirement and caused that category finding to fail.
Use those matched rules as the primary evidence for what must be
corrected.

HOW TO READ THE RULES BELOW:
- An entry with "include_at_least_one_of" is a CHECK category. The
  requirement passes only if its text contains at least one of those
  exact phrases (case-insensitive, as plain text). Work one of them
  naturally into the sentence.
- Under "actually_matched_rules" are ISSUE rules that matched. Remove or
  rephrase exactly those words/phrases without changing the meaning, and
  do not introduce other listed rule words.

RELEVANT MASTER MODULE RULES (failed categories only; rules already listed
under actually_matched_rules are not repeated):
{rules_json}

STRICT SUGGESTION DECISION:

- If ANY Rule Engine finding has passed=false, return EXACTLY ONE
  comprehensive suggestion.

- If ALL Rule Engine findings have passed=true, return ZERO suggestions.

- Never return more than one suggestion.

- Never create a suggestion merely because an AI quality dimension
  needs improvement when every Rule Engine check passed.

WHEN RULE ENGINE CHECKS FAIL:

The ONE suggestion must address EVERY failed check.

The suggestion must contain:

1. suggestion_text:
   A concise explanation of what has been corrected.

2. suggestion_type:
   One valid suggestion type.

3. resolved_requirement_text:
   ONE complete standalone corrected requirement.

The resolved requirement must:

- preserve the original intent;
- address every failed Rule Engine check;
- preserve the passing status of every currently passing Rule Engine check;
- use the supplied Master Module rules;
- make only changes needed to address the failed checks;
- not add behavior, delivery channels, conditions, or required information
    that is not supported by the original requirement;
- actually change the requirement where correction is required;
- not simply repeat the original requirement;
- not invent unsupported facts.

The resolved requirement may be internally reviewed against the failed
Rule Engine checks when internal resolution is enabled by the service.

When a failed category is a compound-requirement category, use the
actually matched configured rule(s) to correct the requirement. Produce
one atomic requirement and do not simply replace one configured compound
trigger with another configured compound trigger.

QUALITY ASSESSMENT:

Evaluate the CURRENT REQUIREMENT using exactly these six dimensions:

1. clarity
2. completeness
3. unambiguity
4. consistency
5. specificity
6. testability

For every dimension return exactly one:

"Good"
"Needs improvement"
"Poor"

Return all six fields.

If there is no meaningful ambiguity, unambiguity should normally be "Good".

Keep analysis_summary concise.
Keep issues to at most 2 concise items.

IMPORTANT OUTPUT CONTRACT:

- failed Rule Engine checks -> exactly 1 suggestion
- no failed Rule Engine checks -> 0 suggestions
- every suggestion must have:
  suggestion_text
  suggestion_type
  resolved_requirement_text
- return the result as a single valid JSON object
"""

        base_prompt = render_prompt("[]", "[]")
        data_budget = max(
            600,
            MAX_PROMPT_TOKENS
            - self._estimate_tokens(base_prompt)
            - self._estimate_tokens(requirement_text[:3500]),
        )
        context = self._build_prompt_context(
            rule_findings,
            master_rules,
            data_budget,
        )
        prompt = render_prompt(
            context["findings_json"],
            context["rules_json"],
        )

        print(
            "[AI ANALYSIS] Analysis prompt ~"
            f"{self._estimate_tokens(prompt)} tokens "
            f"(limit {MAX_PROMPT_TOKENS})."
        )

        request_kwargs = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0,
            "max_completion_tokens": MAIN_MAX_COMPLETION_TOKENS,
            "reasoning_effort": "low",
            "include_reasoning": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "reqintel_requirement_analysis",
                    "strict": True,
                    "schema": self._build_main_schema(),
                }
            }
        }

        try:
            raw_content = await self._call_groq(
                request_kwargs
            )

            data = json.loads(raw_content)

            quality = data.get(
                "quality_assessment"
            )

            if not isinstance(
                quality,
                dict
            ):
                raise RuntimeError(
                    "Groq response is missing quality_assessment"
                )

            required_quality_fields = [
                "clarity",
                "completeness",
                "unambiguity",
                "consistency",
                "specificity",
                "testability",
            ]

            missing_fields = [
                field
                for field in required_quality_fields
                if not quality.get(field)
            ]

            if missing_fields:
                raise RuntimeError(
                    "Groq response is missing quality fields: "
                    + ", ".join(missing_fields)
                )

            for field in required_quality_fields:
                value = str(
                    quality[field]
                ).strip()

                if value not in QUALITY_LABELS:
                    raise RuntimeError(
                        f"Invalid quality value for "
                        f"{field}: {value}"
                    )

                quality[field] = value

            data["ambiguity_detected"] = (
                str(
                    quality["unambiguity"]
                ).strip()
                != "Good"
            )

            issues = data.get(
                "issues",
                []
            )

            if not isinstance(
                issues,
                list
            ):
                raise RuntimeError(
                    "Groq response contains an invalid issues field"
                )

            data["issues"] = [
                str(issue).strip()
                for issue in issues
                if str(issue).strip()
            ][:2]

            suggestions = data.get(
                "suggestions",
                []
            )

            if not isinstance(
                suggestions,
                list
            ):
                raise RuntimeError(
                    "Groq response contains an invalid suggestions field"
                )

            if failed_rule_findings:

                if len(suggestions) != 1:
                    raise RuntimeError(
                        "Exactly one comprehensive suggestion is required "
                        "when at least one Rule Engine check fails"
                    )

                suggestion = suggestions[0]

                suggestion_type = str(
                    suggestion.get(
                        "suggestion_type"
                    )
                    or "other"
                )

                if suggestion_type not in (
                    ALLOWED_SUGGESTION_TYPES
                ):
                    suggestion_type = "other"

                suggestion["suggestion_type"] = (
                    suggestion_type
                )

                initial_resolved_text = str(
                    suggestion.get(
                        "resolved_requirement_text"
                    )
                    or ""
                ).strip()

                if not initial_resolved_text:
                    raise RuntimeError(
                        "Groq response contains a suggestion "
                        "without resolved_requirement_text"
                    )

                # ---------------------------------------------------
                # V1:
                #
                # First analysis must show the actual Rule Engine
                # result and the AI suggestion directly.
                #
                # NO internal resolution is performed here.
                # ---------------------------------------------------
                if not resolve_failed_requirement:

                    suggestion[
                        "resolved_requirement_text"
                    ] = initial_resolved_text

                    suggestion_text = str(
                        suggestion.get(
                            "suggestion_text"
                        )
                        or ""
                    ).strip()

                    if not suggestion_text:
                        suggestion_text = (
                            "The requirement was revised to address "
                            "the failed Rule Engine checks."
                        )

                    suggestion[
                        "suggestion_text"
                    ] = suggestion_text

                    data["suggestions"] = [
                        suggestion
                    ]

                    print(
                        "[AI ANALYSIS] Initial repository analysis. "
                        "Returning the AI suggestion without "
                        "internal resolution."
                    )

                # ---------------------------------------------------
                # V2+:
                #
                # Accepted draft has created the new repository
                # version. Internal AI resolution is now enabled.
                # ---------------------------------------------------
                else:

                    print(
                        "[AI ANALYSIS] Version requires internal "
                        "resolution validation."
                    )

                    final_resolved_text = (
                        await self._resolve_failed_requirement(
                            original_requirement=requirement_text,
                            candidate_requirement=(
                                initial_resolved_text
                            ),
                            failed_findings=(
                                failed_rule_findings
                            ),
                            relevant_master_rules=(
                                master_rules
                            ),
                        )
                    )

                    suggestion[
                        "resolved_requirement_text"
                    ] = final_resolved_text

                    suggestion_text = str(
                        suggestion.get(
                            "suggestion_text"
                        )
                        or ""
                    ).strip()

                    if not suggestion_text:
                        suggestion_text = (
                            "The requirement was revised to address "
                            "all failed Rule Engine checks."
                        )

                    suggestion[
                        "suggestion_text"
                    ] = suggestion_text

                    data["suggestions"] = [
                        suggestion
                    ]

                    print(
                        "[AI ANALYSIS] Final resolved requirement "
                        "generated after internal validation."
                    )

            else:

                data["suggestions"] = []

                print(
                    "[AI ANALYSIS] Rule Engine is clean. "
                    "No AI suggestion generated."
                )

            result = AIAnalysisResult.model_validate(
                data
            )

            print(
                "[AI ANALYSIS] Successfully generated structured "
                "quality assessment."
            )

            return result

        except Exception as exc:

            print(
                "[AI ANALYSIS] Failed to process Groq response: "
                f"{exc}"
            )

            raise RuntimeError(
                f"Groq AI analysis failed: {exc}"
            ) from exc
    async def suggest_traceability_links(
        self,
        requirements: list[dict[str, Any]],
        existing_links: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(requirements) < 2:
            return []

        requirement_context = [
            {
                "id": str(req["id"]),
                "code": req.get("requirement_code"),
                "title": req.get("title") or "",
                "text": str(
                    req.get("current_requirement_text")
                    or req.get("title")
                    or ""
                )[:2000],
            }
            for req in requirements
        ]

        existing_pairs = [
            {
                "source_requirement_id": str(
                    link["source_requirement_id"]
                ),
                "target_requirement_id": str(
                    link["target_requirement_id"]
                ),
            }
            for link in existing_links
        ]

        prompt = f"""
You are ReqIntel, a software requirements traceability assistant.

Analyze the project requirements and suggest meaningful traceability
relationships between different requirements.

REQUIREMENTS:
{json.dumps(requirement_context, ensure_ascii=False)}

EXISTING TRACEABILITY LINKS:
{json.dumps(existing_pairs, ensure_ascii=False)}

RULES:
1. Suggest only relationships supported by the requirement text.
2. Do not create links from a requirement to itself.
3. Do not suggest relationships already present in existing links,
   including the reverse direction.
4. Do not force a relationship when none is justified.
5. Multiple links may be suggested for one requirement.
6. Use only requirement IDs provided above.
7. Use link_type "relates_to" for every suggestion.
8. Give a concise reason explaining the relationship.
9. match_score must be an integer from 0 to 100.
10. Return at most 20 suggestions.
11. Return JSON only.

Return this structure:
{{
  "suggestions": [
    {{
      "source_requirement_id": "existing requirement ID",
      "target_requirement_id": "existing requirement ID",
      "link_type": "relates_to",
      "match_score": 85,
      "reason": "Explanation of the relationship"
    }}
  ]
}}
"""

        request_kwargs = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "reasoning_effort": "low",
            "include_reasoning": False,
            "response_format": {
                "type": "json_object",
            },
        }

        raw_content = await self._call_groq(request_kwargs)
        data = json.loads(raw_content)

        valid_requirements = {
            str(req["id"]): req for req in requirements
        }

        existing_pair_set = {
            (
                str(link["source_requirement_id"]),
                str(link["target_requirement_id"]),
            )
            for link in existing_links
        }

        existing_pair_set |= {
            (target, source)
            for source, target in existing_pair_set
        }

        suggestions = []
        seen_pairs = set()
        for item in data.get("suggestions", []):
            source_id = str(item.get("source_requirement_id", ""))
            target_id = str(item.get("target_requirement_id", ""))

            if source_id not in valid_requirements:
                continue

            if target_id not in valid_requirements:
                continue

            if source_id == target_id:
                continue

            if (source_id, target_id) in existing_pair_set:
                continue

            source = valid_requirements[source_id]
            target = valid_requirements[target_id]

            try:
                score = max(
                    0,
                    min(100, int(item.get("match_score", 0))),
                )
            except (TypeError, ValueError):
                score = 0
            pair = frozenset((source_id, target_id))

            if pair in seen_pairs:
                continue

            seen_pairs.add(pair)

            suggestions.append({
                "source_requirement_id": source_id,
                "target_requirement_id": target_id,
                "source_requirement_code": source.get(
                    "requirement_code"
                ),
                "target_requirement_code": target.get(
                    "requirement_code"
                ),
                "target_requirement_title": target.get("title"),
                "target_requirement_text": str(
                    target.get("current_requirement_text")
                    or target.get("title")
                    or ""
                ),
                "link_type": "relates_to",
                "match_score": score,
                "reason": str(item.get("reason") or "").strip(),
            })

        suggestions.sort(
            key=lambda item: item["match_score"],
            reverse=True,
        )

        return suggestions[:20]

    async def analyze_traceability_impact(
        self,
        source_requirement: dict[str, Any],
        affected_requirements: list[dict[str, Any]],
        traceability_links: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not affected_requirements:
            return []

        source = {
            "id": str(source_requirement["id"]),
            "code": source_requirement.get("requirement_code"),
            "title": source_requirement.get("title") or "",
            "text": str(
                source_requirement.get("current_requirement_text")
                or source_requirement.get("title")
                or ""
            )[:2000],
        }

        affected = [
            {
                "id": str(req["id"]),
                "code": req.get("requirement_code"),
                "title": req.get("title") or "",
                "text": str(
                    req.get("current_requirement_text")
                    or req.get("title")
                    or ""
                )[:2000],
            }
            for req in affected_requirements
        ]

        valid_ids = {req["id"] for req in affected}

        relevant_links = [
            {
                "source_requirement_id": str(link["source_requirement_id"]),
                "target_requirement_id": str(link["target_requirement_id"]),
                "link_type": link.get("link_type") or "relates_to",
            }
            for link in traceability_links
            if (
                str(link.get("source_requirement_id")) == source["id"]
                or str(link.get("target_requirement_id")) == source["id"]
            )
        ]

        prompt = f"""
You are ReqIntel, an expert software requirements impact analyst.

Evaluate how a change to the SOURCE REQUIREMENT could affect each
AFFECTED REQUIREMENT.

SOURCE REQUIREMENT:
{json.dumps(source, ensure_ascii=False)}

AFFECTED REQUIREMENTS:
{json.dumps(affected, ensure_ascii=False)}

TRACEABILITY RELATIONSHIPS:
{json.dumps(relevant_links, ensure_ascii=False)}

Evaluate using:
1. Semantic similarity and functional dependency between requirements.
2. The actual meaning and scope of their requirement text.
3. The traceability relationship type and direction.
4. Potential effects on functionality, data, interfaces, security,
   workflows, and testing.

Risk levels:
- critical: change could cause a major system-wide or severe impact.
- high: substantial functional, security, or dependency impact.
- medium: partial or limited functional impact.
- low: minor or indirect impact.

Do not assign risk based only on keywords or number of links.
Do not invent dependencies unsupported by the supplied information.
Return one result for each affected requirement.
Use only the affected requirement IDs provided.
Return JSON only in this format:

{{
  "impacts": [
    {{
      "affected_requirement_id": "existing ID",
      "risk_level": "high",
      "impact_description": "Concise explanation of the impact"
    }}
  ]
}}
"""

        request_kwargs = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "reasoning_effort": "low",
            "include_reasoning": False,
            "response_format": {"type": "json_object"},
        }

        raw_content = await self._call_groq(request_kwargs)
        data = json.loads(raw_content)

        results = []
        seen_ids = set()

        for item in data.get("impacts", []):
            affected_id = str(item.get("affected_requirement_id", ""))
            risk_level = str(item.get("risk_level", "")).lower()

            if affected_id not in valid_ids or affected_id in seen_ids:
                continue

            if risk_level not in {"low", "medium", "high", "critical"}:
                continue

            description = str(
                item.get("impact_description") or ""
            ).strip()

            if not description:
                continue

            seen_ids.add(affected_id)

            results.append({
                "affected_requirement_id": affected_id,
                "risk_level": risk_level,
                "impact_description": description,
                "ai_generated": True,
            })

        return results
