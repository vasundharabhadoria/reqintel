import json
import os
import re
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field


load_dotenv(override=True)


class ExtractedRequirement(BaseModel):
    type: Literal[
        "functional",
        "non-functional",
        "business-rule",
        "constraint",
        "security",
        "other",
    ]
    text: str = Field(
        description="The exact requirement statement extracted from the document"
    )


class RequirementExtractionResult(BaseModel):
    is_srs: bool
    requirements: list[ExtractedRequirement]


class AIRequirementExtractionStrategy:

    MODEL = "openai/gpt-oss-20b"

    def __init__(self):
        token = os.getenv("GROQ_API_KEY")

        if not token:
            raise ValueError("GROQ_API_KEY is not configured in .env")

        self.client = Groq(api_key=token)
        # Free fallback provider used when Groq quota is exhausted.
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "openrouter/free")

    # ---------------------------------------------------------
    # MAIN EXTRACTION
    # ---------------------------------------------------------

    def identify_structured(
        self,
        content: str,
    ) -> RequirementExtractionResult:

        if not content or not content.strip():
            return RequirementExtractionResult(
                is_srs=False,
                requirements=[],
            )

        print(
            f"[AI Extraction] Document length: {len(content)} characters"
        )

        extraction_start = time.perf_counter()

               # Fast local SRS detection — no AI/API call.
        srs_keywords = (
            "software requirements specification",
            "system requirements specification",
            "functional requirements",
            "non-functional requirements",
            "functional requirement",
            "non-functional requirement",
            "requirements specification",
            "requirement specification",
        )

        sample = content[:20000].lower()

        if not any(keyword in sample for keyword in srs_keywords):
            print("[AI Extraction] Document does not appear to be an SRS.")

            return RequirementExtractionResult(
                is_srs=False,
                requirements=[],
            )

        print("[AI Extraction] Document accepted as SRS.")

        chunks = self._split_into_chunks(
            content,
            max_chars=6000,
        )

        all_requirements: list[ExtractedRequirement] = []

        print(
            f"[AI Extraction] Number of chunks: {len(chunks)}"
        )

        # -----------------------------------------------------
        # PROCESS CHUNKS IN PARALLEL
        # -----------------------------------------------------

        def process_chunk(args):
            index, chunk = args

            print(
                f"[AI Extraction] Processing chunk "
                f"{index}/{len(chunks)} "
                f"({len(chunk)} chars)"
            )

            return index, self._process_chunk(
                chunk=chunk,
                chunk_number=index,
            )

        with ThreadPoolExecutor(max_workers=3) as executor:

            results = executor.map(
                process_chunk,
                enumerate(chunks, start=1),
            )

            failed_chunks: list[int] = []

            for index, result in results:

                if result is None:
                    print(
                        f"[AI Extraction] Chunk {index}/{len(chunks)} failed. "
                        "Continuing with successful chunks."
                    )
                    failed_chunks.append(index)
                    continue

                all_requirements.extend(result.requirements)

        total_time = time.perf_counter() - extraction_start

        # -----------------------------------------------------
        # REMOVE DUPLICATES
        # -----------------------------------------------------

        unique_requirements: list[ExtractedRequirement] = []
        seen: set[str] = set()

        for requirement in all_requirements:

            text = requirement.text.strip()

            if not text:
                continue
            
            # Reject descriptive UI/capability statements unless explicitly normative.
            lower_text = text.lower()
            
            # Reject assumptions, environment dependencies, and descriptive UI statements.
            reject_patterns = (
                r"^users possess ",
                r"^uploaded documents contain ",
                r"^.*libraries are available",
                r"^.*database services are available",
                r"^.*is installed and configured",
                r"^a stable network connection is available",
                r"^the following documentation will accompany",
                r"^the interface is designed to ",
                r"^the major user interface components include",
                r"^the user interface is designed to ",
            )
            if any(re.search(pattern, lower_text) for pattern in reject_patterns):
                continue

            descriptive_prefixes = (
                "the system provides ",
                "the system includes ",
                "the system offers ",
                "the system has ",
                "the platform provides ",
                "the platform includes ",
                "the interface provides ",
                "the interface includes ",
                "reqintel provides ",
            )
            if lower_text.startswith(descriptive_prefixes) and not any(
                word in lower_text
                for word in (" shall ", " must ", " required to ", " is required to ")
            ):
                continue


            key = re.sub(
                r"\s+",
                " ",
                text.lower(),
            )

            if key not in seen:
                seen.add(key)
                unique_requirements.append(requirement)

        print(
            f"[AI Extraction] Final requirements: "
            f"{len(unique_requirements)}"
        )

        print(
            f"[AI Extraction] Total extraction time: "
            f"{total_time:.2f} seconds"
        )
        if failed_chunks:
            print(
                f"[AI Extraction] Warning: failed chunks: {failed_chunks}. "
                f"Using {len(chunks) - len(failed_chunks)}/{len(chunks)} successful chunks."
            )

        if not unique_requirements:
            raise RuntimeError(
                "Requirement extraction failed: no requirements were extracted."
            )

        return RequirementExtractionResult(
            is_srs=True,
            requirements=unique_requirements,
        )

    # ---------------------------------------------------------
    # DOCUMENT-LEVEL SRS CLASSIFICATION
    # ---------------------------------------------------------

    def _is_srs_document(self, sample: str) -> bool:

        start_time = time.perf_counter()

        print(
            f"[SRS Check] Classifying document sample "
            f"({len(sample)} chars)"
        )

        prompt = """
You are an expert software requirements document classifier.

Decide whether the PROVIDED DOCUMENT SAMPLE is part of a genuine
Software Requirements Specification (SRS) or equivalent software
requirements specification document.

Return true when the document is clearly a software requirements
specification, even if its template or section names differ.

Strong evidence includes:
- Software Requirements Specification / SRS title
- purpose or scope describing software requirements
- functional requirements or system features
- non-functional requirements
- external interface requirements
- performance, security, safety, quality, business rules,
  constraints, assumptions, dependencies, or other normative
  software requirements
- numbered requirement statements

Do NOT classify a document as SRS merely because it mentions the
word "requirement".

Resumes, proposals, project reports, user manuals, marketing
documents, meeting notes, source code, general essays, and ordinary
business documents are not SRS documents unless the sample clearly
functions as a software requirements specification.

Return ONLY valid JSON in exactly this format:

{
  "is_srs": true
}

or

{
  "is_srs": false
}

DOCUMENT SAMPLE:
""" + sample

        try:

            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=0,
                max_completion_tokens=2048,
reasoning_effort="low",
include_reasoning=False,
             
            )

            elapsed = time.perf_counter() - start_time
            raw = response.choices[0].message.content or ""

            data = json.loads(raw)

            is_srs = bool(data.get("is_srs", False))

            print(
                f"[SRS Check] Result: {is_srs} | "
                f"{elapsed:.2f}s"
            )

            return is_srs

        except Exception as exc:

            elapsed = time.perf_counter() - start_time

            print(
                f"[SRS Check Error] {elapsed:.2f}s | {exc}"
            )

            return False

    # ---------------------------------------------------------
    # PROCESS ONE CHUNK
    # ---------------------------------------------------------

    def _process_chunk(
        self,
        chunk: str,
        chunk_number: int,
    ) -> RequirementExtractionResult | None:

        result = self._ask_ai(
            chunk,
            chunk_number=chunk_number,
        )

        if result is not None:
            return result

        print(
            f"[AI Extraction] Chunk {chunk_number} "
            f"returned invalid response."
        )

        return None

    # ---------------------------------------------------------
    # CALL GROQ / QWEN
    # ---------------------------------------------------------

    def _ask_ai(
        self,
        chunk: str,
        chunk_number: int,
    ) -> RequirementExtractionResult | None:

        start_time = time.perf_counter()

        print(
            f"[AI Request] Chunk {chunk_number} "
            f"| {len(chunk)} chars"
        )

        prompt = """
You are an expert Software Requirements Analyst.

Extract only genuine software requirements explicitly stated in this SRS chunk.

Rules:
1. Do not invent, infer, strengthen, or rewrite requirements.
2. Preserve the source wording as closely as possible.
3. Extract functional, non-functional, security, business-rule, legal/privacy/compliance,
   measurable performance, and genuine software constraints when explicitly stated.
4. A requirement does not need "shall" or "must" if the source clearly expresses
   a normative obligation, required behavior, measurable target, constraint, or rule.
5. Do not extract headings, titles, IDs, examples, explanatory prose, goals, benefits,
   generic descriptions, capabilities, features, or future plans.
6. Do not extract workflow/use-case steps, implementation steps, short action fragments,
   or internal processing steps unless explicitly stated as a normative requirement.
7. Do not extract technology names or design choices unless explicitly mandatory.
8. Do not extract database schema/design details such as tables, keys, indexes,
   columns, ORM details, SQL, internal IDs, or storage implementation details unless
   explicitly stated as an externally applicable software requirement.
9. Do not extract hardware/infrastructure details unless explicitly mandatory for
   software deployment.
10. Each item must independently express a complete requirement.
11. Do not create duplicates.
12. Extract every genuine requirement present in this chunk.
13. The response MUST be exactly ONE JSON OBJECT, never a JSON array.
14. NEVER wrap the response in [ ].
15. The top-level JSON object MUST contain exactly "is_srs" and "requirements".
16. For laws, regulations, privacy, or compliance, use "constraint" or "other".
17. You may use a descriptive requirement type when useful; the application will normalize it.
18. Extract every genuine requirement present in the chunk; do not omit requirements just to keep the response short.

Allowed types:
functional
non-functional
business-rule
constraint
security
other

Return ONLY valid JSON in exactly this structure:

{
  "is_srs": true,
  "requirements": [
    {
      "type": "functional",
      "text": "exact requirement text from source"
    }
  ]
}

If there are no genuine requirements:

{
  "is_srs": true,
  "requirements": []
}

SRS CHUNK:
""" + chunk

        try:


            response = None
            max_attempts = 2

            for attempt in range(1, max_attempts + 1):
                try:
                    response = self.client.chat.completions.create(
                        model=self.MODEL,
                        messages=[
                            {
                                "role": "user",
                                "content": prompt,
                            }
                        ],
                        temperature=0,
                        max_completion_tokens=4096,
                        reasoning_effort="low",
                        include_reasoning=False,
                        response_format={
                            "type": "json_schema",
                            "json_schema": {
                                "name": "requirement_extraction",
                                "strict": True,
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "is_srs": {"type": "boolean"},
                                        "requirements": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "type": {"type": "string"},
                                                    "text": {"type": "string"},
                                                },
                                                "required": ["type", "text"],
                                                "additionalProperties": False,
                                            },
                                        },
                                    },
                                    "required": ["is_srs", "requirements"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                    )
                    break

                except Exception as exc:
                    error_text = str(exc)
                    lower_error = error_text.lower()

                    # Groq daily quota cannot be fixed by retrying. Fall back
                    # immediately to Gemini when a key is configured.
                    if "tokens per day" in lower_error:
                        print(
                            f"[AI Fallback] Chunk {chunk_number} | "
                            "Groq daily token limit reached."
                        )
                        response = self._ask_openrouter(
                            prompt, chunk_number=chunk_number
                        )
                        if response is not None:
                            break
                        print(
                            f"[AI Request Error] Chunk {chunk_number} | "
                            "Groq quota reached and Gemini fallback failed."
                        )
                        return None

                    retryable = (
                        "429" in lower_error
                        or "rate limit" in lower_error
                        or "timeout" in lower_error
                        or "timed out" in lower_error
                        or "connection" in lower_error
                        or "502" in lower_error
                        or "503" in lower_error
                        or "504" in lower_error
                    )

                    if not retryable or attempt == max_attempts:
                        print(
                            f"[AI Request Error] Chunk {chunk_number} | "
                            f"attempt {attempt}/{max_attempts} | {exc}"
                        )
                        # For a 429 that is not TPD, use Gemini too.
                        if "429" in lower_error and self.gemini_api_key:
                            response = self._ask_openrouter(
                                prompt, chunk_number=chunk_number
                            )
                            if response is not None:
                                break
                        return None

                    wait_seconds = 10 * attempt if "429" in lower_error else 2

                    print(
                        f"[AI Retry] Chunk {chunk_number} | "
                        f"attempt {attempt}/{max_attempts} | "
                        f"waiting {wait_seconds}s"
                    )
                    time.sleep(wait_seconds)

            if response is None:
                return None

            # Gemini fallback returns the raw JSON text in a lightweight
            # response-compatible tuple.
            if isinstance(response, str):
                raw = response
            else:
                raw = response.choices[0].message.content or ""
            elapsed = time.perf_counter() - start_time
            print(f"[AI Raw Response] Chunk {chunk_number} | {len(raw)} chars")

            print(
                f"[AI Response] Chunk {chunk_number} "
                f"| {elapsed:.2f}s"
            )

            data = json.loads(raw)

            def is_schema_or_sql_detail(text: str) -> bool:
                """Reject database/schema implementation fragments, not real requirements."""
                import re

                value = " ".join(str(text).strip().split())
                if not value:
                    return True

                schema_patterns = (
                    r"\bNOT\s+NULL\b",
                    r"\bPRIMARY\s+KEY\b",
                    r"\bFOREIGN\s+KEY\b",
                    r"\bREFERENCES\s+[A-Za-z_][\w$]*\s*\(",
                    r"\bCHECK\s*\(",
                    r"\bBIGSERIAL\b",
                    r"\bAUTO[- ]?INCREMENT(?:ING)?\b",
                    r"\bCREATE\s+TABLE\b",
                    r"\bALTER\s+TABLE\b",
                    r"\bCREATE\s+INDEX\b",
                    r"\bINSERT\s+INTO\b",
                    r"\bSELECT\s+.+\s+FROM\b",
                    r"\bUPDATE\s+.+\s+SET\b",
                    r"\bDELETE\s+FROM\b",
                )

                return any(re.search(pattern, value, re.IGNORECASE) for pattern in schema_patterns)

            type_map = {
                "functional": "functional",
                "functional requirement": "functional",
                "non-functional": "non-functional",
                "nonfunctional": "non-functional",
                "non functional": "non-functional",
                "performance": "non-functional",
                "usability": "non-functional",
                "reliability": "non-functional",
                "availability": "non-functional",
                "scalability": "non-functional",
                "business-rule": "business-rule",
                "business rule": "business-rule",
                "business": "business-rule",
                "constraint": "constraint",
                "constraints": "constraint",
                "legal": "constraint",
                "compliance": "constraint",
                "privacy": "constraint",
                "security": "security",
                "secure": "security",
                "other": "other",
            }

            filtered_requirements = []

            for item in data.get("requirements", []):
                text = str(item.get("text", "")).strip()

                # LLMs can still return raw SQL/schema fragments even when the
                # prompt explicitly asks them not to. Filter those deterministically.
                if is_schema_or_sql_detail(text):
                    print(
                        f"[AI Filter] Chunk {chunk_number} | "
                        f"Skipped schema/SQL detail: {text[:120]}"
                    )
                    continue

                raw_type = str(item.get("type", "")).strip().lower()
                item["type"] = type_map.get(raw_type, "other")
                item["text"] = text
                filtered_requirements.append(item)

            data["requirements"] = filtered_requirements

            return RequirementExtractionResult.model_validate(data)

        except json.JSONDecodeError as exc:

            elapsed = time.perf_counter() - start_time

            print(
                f"[AI JSON Error] Chunk {chunk_number} "
                f"| {elapsed:.2f}s "
                f"| {exc}"
            )

            return None

        except Exception as exc:

            elapsed = time.perf_counter() - start_time

            print(
                f"[AI Request Error] Chunk {chunk_number} "
                f"| {elapsed:.2f}s "
                f"| {exc}"
            )

            return None

    # ---------------------------------------------------------
    # OPENROUTER FREE FALLBACK
    # ---------------------------------------------------------

    def _ask_openrouter(self, prompt: str, chunk_number: int) -> str | None:
        """Use OpenRouter's free-model router when Groq is unavailable."""
        if not self.openrouter_api_key:
            print(
                f"[AI Fallback] Chunk {chunk_number} | "
                "OPENROUTER_API_KEY is not configured."
            )
            return None

        try:
            url = "https://openrouter.ai/api/v1/chat/completions"

            payload = {
                "model": self.openrouter_model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "temperature": 0,
                "max_tokens": 2048,
                "stream": False,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "requirement_extraction",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "is_srs": {"type": "boolean"},
                                "requirements": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "type": {"type": "string"},
                                            "text": {"type": "string"}
                                        },
                                        "required": ["type", "text"],
                                        "additionalProperties": False
                                    }
                                }
                            },
                            "required": ["is_srs", "requirements"],
                            "additionalProperties": False
                        }
                    }
                }
            }

            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "HTTP-Referer": "http://localhost",
                    "X-Title": "ReqIntel",
                },
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            choices = data.get("choices", [])
            if not choices:
                print(
                    f"[AI OpenRouter Error] Chunk {chunk_number} | "
                    "No choices returned."
                )
                return None

            raw = choices[0].get("message", {}).get("content", "")
            if isinstance(raw, list):
                raw = "".join(
                    part.get("text", "")
                    for part in raw
                    if isinstance(part, dict)
                )
            raw = str(raw).strip()

            if not raw:
                print(
                    f"[AI OpenRouter Error] Chunk {chunk_number} | "
                    "Empty response."
                )
                return None

            print(
                f"[AI OpenRouter Fallback] Chunk {chunk_number} | "
                "Free model response received."
            )
            return raw

        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(exc)

            print(
                f"[AI OpenRouter Error] Chunk {chunk_number} | "
                f"HTTP {exc.code} | {detail[:500]}"
            )
            return None

        except Exception as exc:
            print(
                f"[AI OpenRouter Error] Chunk {chunk_number} | {exc}"
            )
            return None

    # ---------------------------------------------------------
    # COMPATIBILITY METHOD
    # ---------------------------------------------------------

    def identify(
        self,
        content: str,
    ) -> list[str]:

        result = self.identify_structured(
            content
        )

        if not result.is_srs:
            return []

        return [
            requirement.text
            for requirement in result.requirements
        ]

    # ---------------------------------------------------------
    # CHUNKING
    # ---------------------------------------------------------

    def _split_into_chunks(
        self,
        content: str,
        max_chars: int = 6000,
    ) -> list[str]:

        if not content:
            return []

        paragraphs = [
            paragraph.strip()
            for paragraph in content.split("\n\n")
            if paragraph.strip()
        ]

        chunks: list[str] = []
        current_chunk = ""

        for paragraph in paragraphs:

            if len(paragraph) <= max_chars:

                if (
                    current_chunk
                    and len(current_chunk)
                    + len(paragraph)
                    + 2
                    <= max_chars
                ):

                    current_chunk += (
                        "\n\n" + paragraph
                    )

                else:

                    if current_chunk:
                        chunks.append(
                            current_chunk
                        )

                    current_chunk = paragraph

                continue

            sentences = re.split(
                r"(?<=[.!?])\s+",
                paragraph,
            )

            for sentence in sentences:

                sentence = sentence.strip()

                if not sentence:
                    continue

                if (
                    current_chunk
                    and len(current_chunk)
                    + len(sentence)
                    + 1
                    <= max_chars
                ):

                    current_chunk += (
                        " " + sentence
                    )

                elif len(sentence) <= max_chars:

                    if current_chunk:
                        chunks.append(
                            current_chunk
                        )

                    current_chunk = sentence

                else:

                    if current_chunk:
                        chunks.append(
                            current_chunk
                        )

                    current_chunk = ""

                    for start in range(
                        0,
                        len(sentence),
                        max_chars,
                    ):

                        piece = sentence[
                            start:start + max_chars
                        ].strip()

                        if piece:
                            chunks.append(piece)

        if current_chunk:
            chunks.append(current_chunk)

        return chunks













