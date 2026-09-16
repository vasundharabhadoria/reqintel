import json
import os
import re
import time
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

    MODEL = "qwen/qwen3.8-27b"

    def __init__(self):
        token = os.getenv("GROQ_API_KEY")

        if not token:
            raise ValueError("GROQ_API_KEY is not configured in .env")

        self.client = Groq(api_key=token)

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

        # Document-level classification.
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
            max_chars=9000,
        )

        all_requirements: list[ExtractedRequirement] = []

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
                max_tokens=900,
                response_format={
                    "type": "json_object"
                },
            )

            elapsed = time.perf_counter() - start_time

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

The document has already been classified as a genuine Software
Requirements Specification (SRS).

Extract ALL genuine software requirements from the provided SRS chunk.

IMPORTANT RULES:

1. Extract only requirements explicitly supported by the source.
2. NEVER invent, infer, or strengthen a requirement.
3. Preserve source wording as closely as possible.
4. Do not convert a feature, capability, goal, benefit, or description
   into a requirement.
5. Do not rewrite ordinary statements into "The system shall..."
   unless the source itself expresses that obligation.
6. Extract functional requirements.
7. Extract non-functional requirements such as performance, security,
   usability, reliability, availability, quality, etc. when explicitly
   stated.
8. Extract explicit business rules.
9. Extract only constraints that impose a genuine obligation on the software or its users. Do NOT extract database schema definitions, SQL statements, PRIMARY KEY, FOREIGN KEY, CHECK constraints, indexes, column definitions, table structures, ORM details, or implementation metadata. Do NOT extract technology names such as React, FastAPI, PostgreSQL, Docker, Ollama, PyMuPDF, or python-docx merely because they appear in the document. A technology choice is a requirement ONLY when the source explicitly states that the system MUST use that technology as a mandatory constraint.
10. Extract explicit security and access-control requirements.
11. Extract explicit database requirements when stated as requirements
    or constraints.
12. Extract measurable performance requirements.
13. Extract legal, privacy, safety, compliance and internationalization
    requirements when explicitly stated.
14. Ignore examples and explanatory prose that do not state a requirement.
15. Ignore section headings and titles.
16. NEVER extract a use-case ID/title by itself.
17. If a use case contains actual requirement statements, extract those
    requirement statements, not the use-case title.
18. Do not create duplicate requirements.
19. A requirement does NOT have to contain "shall" or "must" if the source
    clearly states a normative obligation, expected behavior, measurable
    quality target, constraint, or rule.
20. Do NOT extract design decisions or technology choices merely because
    they are mentioned.
21. Do NOT extract future enhancements or future plans.
22. Do NOT extract generic descriptions of the system.
23. Do NOT extract workflow steps, process steps, activity descriptions, or short action fragments such as "Validate information", "Create project", "Extract text", "Identify requirements", "Generate report", or "Display requirements". Extract them only when the source explicitly states the action as a normative requirement describing required system behavior.
24. Do NOT extract implementation steps, internal processing steps, sequence-of-operations descriptions, or use-case flow steps as separate requirements.
25. Do NOT extract internal data-model or database-design rules as software requirements. Ignore entity relationships, table relationships, foreign keys, primary keys, indexes, column definitions, cascade behavior, ORM rules, version-storage implementation details, internal analysis records, internal IDs, internal status fields, or database query logic.
26. Do NOT extract statements that only describe how the software is internally implemented or how data is stored. Extract a database or technology constraint only when the SRS explicitly makes it a mandatory externally applicable system constraint.
27. Do NOT extract hardware or infrastructure specifications merely because they describe the development/deployment environment. Extract them only when they are explicitly stated as mandatory system deployment requirements.
28. A business rule must describe a real business/domain policy, authorization rule, or user-visible organizational rule. Do NOT classify internal database relationships or implementation rules as business rules.
29. Each extracted item must independently express a complete requirement.
30. Do NOT extract statements that merely describe what the system offers, contains, displays, provides, includes, or has (for example, "The system provides a Login page", "The system provides a Dashboard", or "The system includes search") unless the source explicitly expresses the statement as a mandatory or normative requirement. Reject fragments, labels, headings, noun phrases, or short workflow actions such as "System validates", "Project is created", "Extract text", "Generate report", or "Display requirements" unless the source explicitly defines the complete statement as a normative requirement.
23. Extract every genuine requirement present in this chunk.

Allowed requirement types:

functional
non-functional
business-rule
constraint
security
other

Return ONLY JSON:

{
  "is_srs": true,
  "requirements": [
    {
      "type": "functional",
      "text": "exact requirement text from source"
    }
  ]
}

If this chunk contains no requirements:

{
  "is_srs": true,
  "requirements": []
}

SRS CHUNK:
""" + chunk

        try:

            response = None

            for attempt in range(3):
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
                        max_tokens=900,
                        response_format={
                            "type": "json_object"
                        },
                    )
                    break
                except Exception as exc:
                    error_text = str(exc)
                    if "429" not in error_text or attempt == 2:
                        raise
                    wait_seconds = 10 * (attempt + 1)
                    print(
                        f"[AI Retry] Chunk {chunk_number} | "
                        f"attempt {attempt + 1}/3 | waiting {wait_seconds}s"
                    )
                    time.sleep(wait_seconds)

            elapsed = time.perf_counter() - start_time
            raw = response.choices[0].message.content or ""

            print(
                f"[AI Response] Chunk {chunk_number} "
                f"| {elapsed:.2f}s"
            )

            data = json.loads(raw)

            return RequirementExtractionResult.model_validate(
                data
            )

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













