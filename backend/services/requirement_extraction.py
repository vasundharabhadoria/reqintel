import io

import fitz  # PyMuPDF
from docx import Document


class ExtractionError(Exception):
    """Raised when text cannot be extracted from a source document."""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF bytes using PyMuPDF."""

    text_parts: list[str] = []

    try:
        document = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        raise ExtractionError(f"Could not open PDF: {exc}") from exc

    try:
        for page in document:
            page_text = page.get_text()
            if page_text:
                text_parts.append(page_text)
    finally:
        document.close()

    return "\n".join(text_parts).strip()


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from DOCX bytes using python-docx."""

    try:
        document = Document(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ExtractionError(f"Could not open DOCX: {exc}") from exc

    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Decode TXT bytes as UTF-8, replacing undecodable characters."""

    return file_bytes.decode("utf-8", errors="replace").strip()


def extract_text(file_bytes: bytes, source_type: str) -> str:
    """Dispatch to the extractor for the given source_type."""

    source_type = source_type.lower()

    if source_type == "pdf":
        return extract_text_from_pdf(file_bytes)
    if source_type == "docx":
        return extract_text_from_docx(file_bytes)
    if source_type == "txt":
        return extract_text_from_txt(file_bytes)

    raise ExtractionError(f"Unsupported source type for extraction: {source_type}")