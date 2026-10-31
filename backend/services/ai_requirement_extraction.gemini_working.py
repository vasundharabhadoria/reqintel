import json
import os
import re
import time
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_huggingface import ChatHuggingFace,HuggingFaceEndpoint


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

    def __init__(self):

        token = os.getenv("HF_TOKEN")

        if not token:
            raise ValueError("HF_TOKEN is not configured in .env")

        self.llm = HuggingFaceEndpoint(
            repo_id="Qwen/Qwen3-32B",
            huggingfacehub_api_token=token,
            max_new_tokens=1536,
            temperature=0.0,
        )

        self.chat_model = ChatHuggingFace(llm=self.llm)

        # Document-level classifier. This is deliberately separate from
        # requirement extraction so a random PDF/TXT cannot be treated as an SRS
        # just because one paragraph contains requirement-like wording.
        self.srs_check_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
You are an expert software requirements document classifier.

Decide whether the PROVIDED DOCUMENT SAMPLE is part of a genuine
Software Requirements Specification (SRS) or equivalent software
requirements specification document.

Return true when the document is clearly a software requirements
specification, even if its template or section names differ.

Strong evidence includes:
- a title such as Software Requirements Specification / SRS
- a purpose/scope describing software requirements
- functional requirements or system features
- non-functional requirements
- external interface requirements
- performance, security, safety, quality, business rules, constraints,
  assumptions, dependencies, or other normative software requirements
- numbered requirement statements

Do NOT classify a document as SRS merely because it mentions the word
"requirement". Resumes, proposals, project reports, user manuals,
marketing documents, meeting notes, source code, general essays, and
ordinary business documents are not SRS documents unless the sample
clearly functions as a software requirements specification.

Return JSON only:
{{
  "is_srs": true
}}

OR:
{{
  "is_srs": false
}}
""",
                ),
                (
                    "human",
                    """
Classify this document sample:

--- BEGIN DOCUMENT SAMPLE ---
{document}
--- END DOCUMENT SAMPLE ---
""",
                ),
            ]
        )

        self.extraction_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
You are an expert Software Requirements Analyst.

The document has already been classified as a Software Requirements
Specification (SRS). Extract the genuine software requirements from the
provided SRS text.

IMPORTANT RULES:

1. Extract only requirements explicitly supported by the source.
2. NEVER invent, infer, or strengthen a requirement.
3. Preserve the source wording as closely as possible.
4. Do not convert a feature, capability, goal, benefit, or description
   into a requirement.
5. Do not rewrite ordinary statements into "The system shall..."
   unless the source itself expresses that obligation.
6. Extract functional requirements.
7. Extract non-functional requirements such as performance, security,
   usability, reliability, availability, quality, etc. when explicitly
   stated.
8. Extract explicit business rules.
9. Extract explicit constraints, data/schema constraints, interface
   constraints, technology constraints, and other normative constraints.
10. Extract explicit security and access-control requirements.
11. Ignore examples and explanatory prose that do not state a requirement.
12. Ignore section headings and titles.
13. NEVER extract a use-case ID/title by itself, for example:
    "UC-07: View Requirement Repository".
14. If a use case contains actual requirement statements, extract the
    requirement statements, not the use-case title.
15. Do not create duplicate requirements.
16. A requirement does NOT have to contain the words "shall" or "must".
    Extract it when the source clearly states a normative obligation,
    constraint, expected behavior, measurable quality target, or rule.
17. Keep technical/database requirements when the SRS explicitly states
    them as required constraints.

Allowed requirement types:
functional
non-functional
business-rule
constraint
security
other

Return EXACTLY this JSON structure:

{{
  "is_srs": true,
  "requirements": [
    {{
      "type": "functional",
      "text": "exact requirement text from source"
    }}
  ]
}}

If this particular chunk contains no requirements, return:

{{
  "is_srs": true,
  "requirements": []
}}

Return JSON only. No markdown. No explanations. No code fences.
""",
                ),
                (
                    "human",
                    """
Extract requirements from this SRS document chunk:

--- BEGIN DOCUMENT CHUNK ---
{document}
--- END DOCUMENT CHUNK ---
""",
                ),
            ]
        )

        self.srs_check_chain = (
            self.srs_check_prompt
            | self.chat_model
            | StrOutputParser()
        )

        self.extraction_chain = (
            self.extraction_prompt
            | self.chat_model
            | StrOutputParser()
        )


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

        # First decide whether the document itself is an SRS. Use the title,
        # TOC and opening material rather than classifying isolated chunks.
        sample = content[:12000]
        if not self._is_srs_document(sample):
            print("[AI Extraction] Document classified as NOT SRS.")
            return RequirementExtractionResult(
                is_srs=False,
                requirements=[],
            )

        print("[AI Extraction] Document classified as SRS.")

        chunks = self._split_into_chunks(
            content,
            max_chars=6000,
        )

        all_requirements: list[ExtractedRequirement] = []
        is_srs = True

        print(
            f"[AI Extraction] Number of chunks: {len(chunks)}"
        )

        for index, chunk in enumerate(chunks, start=1):

            print(
                f"[AI Extraction] Processing chunk "
                f"{index}/{len(chunks)} "
                f"({len(chunk)} chars)"
            )

            result = self._process_chunk(
                chunk=chunk,
                chunk_number=index,
            )

            if result is None:
                print(
                    f"[AI Extraction] Skipping failed chunk "
                    f"{index}/{len(chunks)}"
                )
                continue

            if result.is_srs:
                is_srs = True

            all_requirements.extend(
                result.requirements
            )

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

            key = re.sub(
                r"\s+",
                " ",
                text.lower(),
            )

            if key not in seen:

                seen.add(key)

                unique_requirements.append(
                    requirement
                )

        print(
            f"[AI Extraction] Final requirements: "
            f"{len(unique_requirements)}"
        )

        print(
            f"[AI Extraction] Total extraction time: "
            f"{total_time:.2f} seconds"
        )

        return RequirementExtractionResult(
            is_srs=is_srs,
            requirements=unique_requirements,
        )

    # ---------------------------------------------------------
    # DOCUMENT-LEVEL SRS CLASSIFICATION
    # ---------------------------------------------------------

    def _is_srs_document(self, sample: str) -> bool:
        """Classify the document itself before running extraction."""
        start_time = time.perf_counter()

        print(
            f"[SRS Check] Classifying document sample "
            f"({len(sample)} chars)"
        )

        try:
            response = self.srs_check_chain.invoke(
                {"document": sample}
            )

            elapsed = time.perf_counter() - start_time
            cleaned = response.strip()

            if cleaned.startswith("```"):
                cleaned = re.sub(
                    r"^```(?:json)?\s*",
                    "",
                    cleaned,
                    flags=re.IGNORECASE,
                )
                cleaned = re.sub(r"\s*```$", "", cleaned).strip()

            data = json.loads(cleaned)
            is_srs = bool(data.get("is_srs", False))

            print(
                f"[SRS Check] Result: {is_srs} | {elapsed:.2f}s"
            )
            return is_srs

        except Exception as exc:
            elapsed = time.perf_counter() - start_time
            print(
                f"[SRS Check Error] {elapsed:.2f}s | {exc}"
            )
            # Fail closed: if the document cannot be classified reliably,
            # do not extract requirements from an unknown document.
            return False

    # ---------------------------------------------------------
    # PROCESS ONE CHUNK
    # ---------------------------------------------------------

    def _process_chunk(
        self,
        chunk: str,
        chunk_number: int,
    ) -> RequirementExtractionResult | None:

        # First attempt
        result = self._ask_ai(
            chunk,
            chunk_number=chunk_number,
            attempt=1,
        )

        if result is not None:
            return result

        # -----------------------------------------------------
        # RETRY ONCE WITH SMALLER CHUNKS
        # -----------------------------------------------------

        print(
            f"[AI Extraction] Chunk {chunk_number} "
            f"returned invalid response."
        )

        print(
            f"[AI Extraction] Retrying chunk "
            f"{chunk_number} with smaller pieces..."
        )

        smaller_chunks = self._split_into_chunks(
            chunk,
            max_chars=2500,
        )

        combined_requirements: list[
            ExtractedRequirement
        ] = []

        found_srs = False

        for retry_index, small_chunk in enumerate(
            smaller_chunks,
            start=1,
        ):

            result = self._ask_ai(
                small_chunk,
                chunk_number=chunk_number,
                attempt=f"retry-{retry_index}",
            )

            if result is None:
                continue

            if result.is_srs:
                found_srs = True

            combined_requirements.extend(
                result.requirements
            )

        if found_srs or combined_requirements:

            return RequirementExtractionResult(
                is_srs=found_srs,
                requirements=combined_requirements,
            )

        return None

    # ---------------------------------------------------------
    # CALL AI
    # ---------------------------------------------------------

    def _ask_ai(
        self,
        chunk: str,
        chunk_number: int,
        attempt: str | int,
    ) -> RequirementExtractionResult | None:

        start_time = time.perf_counter()

        print(
            f"[AI Request] Chunk {chunk_number} "
            f"| Attempt {attempt} "
            f"| {len(chunk)} chars"
        )

        try:

            response = self.extraction_chain.invoke(
                {
                    "document": chunk,
                }
            )

            elapsed = time.perf_counter() - start_time

            print(
                f"[AI Response] Chunk {chunk_number} "
                f"| Attempt {attempt} "
                f"| {elapsed:.2f}s"
            )

            cleaned = response.strip()

            # Remove markdown fences if model accidentally adds them.
            if cleaned.startswith("```"):

                cleaned = re.sub(
                    r"^```(?:json)?\s*",
                    "",
                    cleaned,
                    flags=re.IGNORECASE,
                )

                cleaned = re.sub(
                    r"\s*```$",
                    "",
                    cleaned,
                )

                cleaned = cleaned.strip()

            # -------------------------------------------------
            # PARSE JSON
            # -------------------------------------------------

            data = json.loads(cleaned)

            result = RequirementExtractionResult.model_validate(
                data
            )

            return result

        except json.JSONDecodeError as exc:

            elapsed = time.perf_counter() - start_time

            print(
                f"[AI JSON Error] Chunk {chunk_number} "
                f"| Attempt {attempt} "
                f"| {elapsed:.2f}s "
                f"| {exc}"
            )

            return None

        except Exception as exc:

            elapsed = time.perf_counter() - start_time

            print(
                f"[AI Request Error] Chunk {chunk_number} "
                f"| Attempt {attempt} "
                f"| {elapsed:.2f}s "
                f"| {exc}"
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
        max_chars: int = 2500,
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

            # -------------------------------------------------
            # NORMAL PARAGRAPH
            # -------------------------------------------------

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

            # -------------------------------------------------
            # LARGE PARAGRAPH
            # -------------------------------------------------

            sentences = re.split(
                r"(?<=[.!?])\s+",
                paragraph,
            )

            for sentence in sentences:

                sentence = sentence.strip()

                if not sentence:
                    continue

                # -------------------------------------------------
                # SENTENCE FITS
                # -------------------------------------------------

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

                # -------------------------------------------------
                # SENTENCE ITSELF TOO LARGE
                # -------------------------------------------------

                else:

                    if current_chunk:

                        chunks.append(
                            current_chunk
                        )

                        current_chunk = ""

                    # Hard split very long sentence.
                    for start in range(
                        0,
                        len(sentence),
                        max_chars,
                    ):

                        piece = sentence[
                            start:start + max_chars
                        ].strip()

                        if piece:

                            chunks.append(
                                piece
                            )

        # -----------------------------------------------------
        # LAST CHUNK
        # -----------------------------------------------------

        if current_chunk:
            chunks.append(
                current_chunk
            )

        return chunks


