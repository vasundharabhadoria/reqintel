import re
from abc import ABC, abstractmethod

REQUIREMENT_KEYWORDS = [
    "shall",
    "must",
    "should",
    "required to",
    "needs to",
    "will allow",
    "will provide",
    "system shall",
    "system must",
    "the system",
    "system should",
    "users can",
    "user can",
    "users should",
    "user should",
    "the user",
    "allows users",
    "allow users",
    "supports",
    "enable users",
    "enables users",
]
_MIN_STATEMENT_LENGTH = 12
_MAX_STATEMENT_LENGTH = 2000
_LEADING_NUMBERING_RE = re.compile(
    r"^(REQ[-\s]?\d+|\d+(?:\.\d+)*[.)]?)\s*", re.IGNORECASE
)
_WHITESPACE_RE = re.compile(r"\s+")


class RequirementExtractionStrategy(ABC):
    """
    Strategy interface for turning raw extracted document text into a list
    of candidate requirement statements. The API/service layer depends only
    on this interface, so a future NLP/LLM-backed strategy can replace
    RuleBasedExtractionStrategy without any change above this module.
    """

    @abstractmethod
    def identify(self, content: str) -> list[str]:
        """Return a deduplicated list of candidate requirement statements."""


def _clean_statement(text: str) -> str:
    text = text.strip()
    text = _LEADING_NUMBERING_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _looks_like_requirement(text_lower: str) -> bool:
    if not text_lower:
        return False
    return any(keyword in text_lower for keyword in REQUIREMENT_KEYWORDS)


class RuleBasedExtractionStrategy(RequirementExtractionStrategy):
    """
    Keyword/regex-based requirement identification. This is explicitly
    rule-based, not AI/NLP-powered — do not describe it otherwise in UI
    copy or docs.
    """

    def identify(self, content: str) -> list[str]:
        if not content:
            return []

        candidates = self._split_into_candidates(content)
        statements: list[str] = []

        for raw_line in candidates:
            cleaned = _clean_statement(raw_line)

            if len(cleaned) < _MIN_STATEMENT_LENGTH:
                continue
            if len(cleaned) > _MAX_STATEMENT_LENGTH:
                continue
            if not _looks_like_requirement(cleaned.lower()):
                continue

            statements.append(cleaned)

        # De-duplicate while preserving order.
        seen: set[str] = set()
        unique_statements: list[str] = []
        for statement in statements:
            key = statement.lower()
            if key not in seen:
                seen.add(key)
                unique_statements.append(statement)

        return unique_statements

    def _split_into_candidates(self, content: str) -> list[str]:
        lines = [line for line in content.splitlines() if line.strip()]

        # Pathological case: the whole document arrived as one giant line
        # (or extraction collapsed newlines). Falling back to sentence
        # splitting avoids treating the entire document as one requirement.
        if len(lines) <= 1 and len(content) > _MAX_STATEMENT_LENGTH:
            return re.split(r"(?<=[.!?])\s+", content)

        return lines