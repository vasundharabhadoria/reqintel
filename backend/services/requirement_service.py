from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.storage import REQUIREMENT_SOURCES_BUCKET, get_storage_client
from models.requirement import (
    ExtractedRequirementSummary,
    ManualRequirementCreate,
    RequirementResponse,
    RequirementSourceResponse,
    RequirementVersionCreate,
    RequirementVersionResponse,
)
from services.project_repository import ProjectRepository
from services.requirement_extraction import ExtractionError, extract_text
from services.requirement_identification import RuleBasedExtractionStrategy
from services.requirement_repository import RequirementRepository


_ALLOWED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
}

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}

_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


class RequirementService:
    """
    Business logic for Module 2 (Requirements).
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.repo = RequirementRepository(db)
        self.storage = get_storage_client()
        self.extraction_strategy = RuleBasedExtractionStrategy()

    async def _require_project(
        self,
        owner_id: UUID,
        project_id: UUID,
    ) -> None:
        project = await self.projects.get_by_id(
            project_id,
            owner_id,
        )

        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

    async def _require_source(
        self,
        project_id: UUID,
        source_id: UUID,
    ) -> dict:
        source = await self.repo.get_source(
            source_id,
            project_id,
        )

        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requirement source not found.",
            )

        return source

    async def _require_requirement(
        self,
        project_id: UUID,
        requirement_id: UUID,
    ) -> dict:
        requirement = await self.repo.get_requirement(
            requirement_id,
            project_id,
        )

        if requirement is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requirement not found.",
            )

        return requirement

    # ---------------------------------------------------------------
    # Sources
    # ---------------------------------------------------------------

    async def list_sources(
        self,
        owner_id: UUID,
        project_id: UUID,
    ) -> list[RequirementSourceResponse]:
        await self._require_project(
            owner_id,
            project_id,
        )

        rows = await self.repo.list_sources(project_id)

        return [
            RequirementSourceResponse.model_validate(row)
            for row in rows
        ]

    async def upload_source(
        self,
        owner_id: UUID,
        project_id: UUID,
        file: UploadFile,
    ) -> RequirementSourceResponse:

        await self._require_project(
            owner_id,
            project_id,
        )

        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file selected.",
            )

        extension = (
            "."
            + file.filename.rsplit(".", 1)[-1].lower()
            if "." in file.filename
            else ""
        )

        source_type = _ALLOWED_EXTENSIONS.get(extension)

        if source_type is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only PDF, DOCX, and TXT files are supported.",
            )

        if (
            file.content_type
            and file.content_type not in _ALLOWED_MIME_TYPES
        ):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="File content type does not match a supported format.",
            )

        file_bytes = await file.read()

        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded file is empty.",
            )

        if len(file_bytes) > _MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File exceeds the 50 MB upload limit.",
            )

        source = await self.repo.create_source(
            project_id=project_id,
            source_type=source_type,
            uploaded_by=owner_id,
            original_filename=file.filename,
            storage_path=None,
            file_size_bytes=len(file_bytes),
            mime_type=file.content_type,
            raw_text=None,
            processing_status="uploaded",
        )

        storage_path = (
            f"{project_id}/{source['id']}{extension}"
        )

        try:
            self.storage.storage.from_(
                REQUIREMENT_SOURCES_BUCKET
            ).upload(
                storage_path,
                file_bytes,
                {
                    "content-type": (
                        file.content_type
                        or "application/octet-stream"
                    )
                },
            )

        except Exception as exc:
            await self.repo.update_source_processing(
                source["id"],
                project_id,
                processing_status="failed",
                extraction_error=f"Storage upload failed: {exc}",
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store the uploaded file.",
            ) from exc

        updated = await self.repo.update_source_processing(
            source["id"],
            project_id,
            processing_status="uploaded",
        )

        await self.db.execute(
            text(
                """
                UPDATE requirement_sources
                SET storage_path = :storage_path
                WHERE id = :source_id
                """
            ),
            {
                "storage_path": storage_path,
                "source_id": source["id"],
            },
        )

        updated["storage_path"] = storage_path

        return RequirementSourceResponse.model_validate(
            updated
        )

    async def get_source_file(
        self,
        owner_id: UUID,
        project_id: UUID,
        source_id: UUID,
    ):
        await self._require_project(
            owner_id,
            project_id,
        )

        source = await self._require_source(
            project_id,
            source_id,
        )

        if not source.get("storage_path"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored file not found.",
            )

        try:
            file_bytes = self.storage.storage.from_(
                REQUIREMENT_SOURCES_BUCKET
            ).download(
                source["storage_path"]
            )

        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve the stored file.",
            ) from exc

        from fastapi.responses import Response

        return Response(
            content=file_bytes,
            media_type=source.get("mime_type")
            or "application/octet-stream",
            headers={
                "Content-Disposition": (
                    f'inline; filename="{source["original_filename"]}"'
                )
            },
        )

    async def extract_source_text(
        self,
        owner_id: UUID,
        project_id: UUID,
        source_id: UUID,
    ) -> RequirementSourceResponse:

        await self._require_project(
            owner_id,
            project_id,
        )

        source = await self._require_source(
            project_id,
            source_id,
        )

        if source["source_type"] == "manual":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manual sources do not require extraction.",
            )

        if not source["storage_path"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This source has no stored file to extract from.",
            )

        await self.repo.update_source_processing(
            source_id,
            project_id,
            processing_status="parsing",
        )

        try:
            file_bytes = self.storage.storage.from_(
                REQUIREMENT_SOURCES_BUCKET
            ).download(
                source["storage_path"]
            )

        except Exception as exc:
            await self.repo.update_source_processing(
                source_id,
                project_id,
                processing_status="failed",
                extraction_error=(
                    f"Could not download stored file: {exc}"
                ),
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve the stored file.",
            ) from exc

        try:
            extracted_text = extract_text(
                file_bytes,
                source["source_type"],
            )

        except ExtractionError as exc:
            await self.repo.update_source_processing(
                source_id,
                project_id,
                processing_status="failed",
                extraction_error=str(exc),
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        if not extracted_text:
            await self.repo.update_source_processing(
                source_id,
                project_id,
                processing_status="failed",
                extraction_error=(
                    "No text could be extracted from the document."
                ),
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No text could be extracted from the document.",
            )

        updated = await self.repo.update_source_processing(
            source_id,
            project_id,
            processing_status="completed",
            raw_text=extracted_text,
        )

        return RequirementSourceResponse.model_validate(
            updated
        )

    # ---------------------------------------------------------------
    # Manual requirement
    # ---------------------------------------------------------------

    async def create_manual_requirement(
        self,
        owner_id: UUID,
        project_id: UUID,
        payload: ManualRequirementCreate,
    ) -> RequirementResponse:

        await self._require_project(
            owner_id,
            project_id,
        )

        source = await self.repo.create_source(
            project_id=project_id,
            source_type="manual",
            uploaded_by=owner_id,
            original_filename=None,
            storage_path=None,
            file_size_bytes=None,
            mime_type=None,
            raw_text=payload.requirement_text,
            processing_status="completed",
        )

        requirement, _version = (
            await self._create_requirement_with_version(
                project_id=project_id,
                source_id=source["id"],
                title=payload.title,
                requirement_text=payload.requirement_text,
                created_by=owner_id,
            )
        )

        return await self.get_requirement(
            owner_id,
            project_id,
            requirement["id"],
        )

    # ---------------------------------------------------------------
    # Requirement identification
    # ---------------------------------------------------------------

    async def extract_requirements(
        self,
        owner_id: UUID,
        project_id: UUID,
        source_id: UUID,
    ) -> ExtractedRequirementSummary:

        await self._require_project(
            owner_id,
            project_id,
        )

        source = await self._require_source(
            project_id,
            source_id,
        )

        if not source["raw_text"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "This source has no extracted text yet. "
                    "Run text extraction first."
                ),
            )

        candidate_statements = (
            self.extraction_strategy.identify(
                source["raw_text"]
            )
        )

        created: list[RequirementResponse] = []

        for statement in candidate_statements:
            title = (
                statement[:80]
                + ("…" if len(statement) > 80 else "")
            )

            requirement, _version = (
                await self._create_requirement_with_version(
                    project_id=project_id,
                    source_id=source_id,
                    title=title,
                    requirement_text=statement,
                    created_by=owner_id,
                )
            )

            created.append(
                await self.get_requirement(
                    owner_id,
                    project_id,
                    requirement["id"],
                )
            )

        return ExtractedRequirementSummary(
            requirements_created=len(created),
            items=created,
        )

    async def _create_requirement_with_version(
        self,
        project_id: UUID,
        source_id: UUID,
        title: str | None,
        requirement_text: str,
        created_by: UUID,
    ) -> tuple[dict, dict]:

        await self.repo.lock_project_for_code_generation(
            project_id
        )

        code = await self.repo.next_requirement_code(
            project_id
        )

        requirement = await self.repo.create_requirement(
            project_id=project_id,
            source_id=source_id,
            requirement_code=code,
            title=title,
            created_by=created_by,
        )

        version = await self.repo.create_version(
            requirement_id=requirement["id"],
            version_number=1,
            requirement_text=requirement_text,
            change_summary="Initial version.",
            created_by=created_by,
        )

        return requirement, version

    # ---------------------------------------------------------------
    # Requirements read/search/filter
    # ---------------------------------------------------------------

    async def list_requirements(
        self,
        owner_id: UUID,
        project_id: UUID,
        status_filter: str | None,
        search: str | None,
        source_id: UUID | None,
    ) -> list[RequirementResponse]:

        await self._require_project(
            owner_id,
            project_id,
        )

        rows = await self.repo.list_requirements(
            project_id,
            status_filter,
            search,
            source_id,
        )

        return [
            RequirementResponse.model_validate(row)
            for row in rows
        ]

    async def get_requirement(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
    ) -> RequirementResponse:

        await self._require_project(
            owner_id,
            project_id,
        )

        row = await self._require_requirement(
            project_id,
            requirement_id,
        )

        return RequirementResponse.model_validate(row)

    # ---------------------------------------------------------------
    # RULE ENGINE
    # ---------------------------------------------------------------

    async def analyze_project_requirements(
        self,
        owner_id: UUID,
        project_id: UUID,
    ) -> dict:

        await self._require_project(
            owner_id,
            project_id,
        )

        requirements = await self.repo.list_requirements(
            project_id,
            None,
            None,
            None,
        )

        from services.rule_engine import analyze_requirements

        rule_engine_input = []

        for req in requirements:
            requirement_text = req.get(
                "current_requirement_text"
            )

            if requirement_text is None:
                requirement_text = req.get(
                    "text",
                    "",
                )

            rule_engine_input.append(
                {
                    "id": str(req["id"]),
                    "text": requirement_text or "",
                }
            )

        results = analyze_requirements(
            rule_engine_input
        )

        if not results:
            await self.db.commit()

            return {
                "total": 0,
                "saved": 0,
                "results": [],
            }

        # -----------------------------------------------------------
        # Fetch the latest version for all requirements in ONE query.
        # -----------------------------------------------------------

        requirement_ids = [
            UUID(str(result["id"]))
            for result in results
        ]

        version_result = await self.db.execute(
            text(
                """
                SELECT DISTINCT ON (requirement_id)
                    id,
                    requirement_id,
                    version_number
                FROM requirement_versions
                WHERE requirement_id IN :requirement_ids
                ORDER BY
                    requirement_id,
                    version_number DESC
                """
            ).bindparams(
                bindparam(
                    "requirement_ids",
                    expanding=True,
                )
            ),
            {
                "requirement_ids": requirement_ids,
            },
        )

        latest_versions = {
            row["requirement_id"]: row["id"]
            for row in version_result.mappings()
        }

        if not latest_versions:
            await self.db.commit()

            return {
                "total": len(results),
                "saved": 0,
                "results": results,
            }

        # -----------------------------------------------------------
        # Delete all old validation rows in ONE query.
        # -----------------------------------------------------------

        version_ids = list(
            latest_versions.values()
        )

        await self.db.execute(
            text(
                """
                DELETE FROM rule_validation
                WHERE requirement_version_id IN :version_ids
                """
            ).bindparams(
                bindparam(
                    "version_ids",
                    expanding=True,
                )
            ),
            {
                "version_ids": version_ids,
            },
        )

        # -----------------------------------------------------------
        # Prepare all validation rows in memory.
        # -----------------------------------------------------------

        validation_rows = []

        for result in results:
            requirement_id = UUID(
                str(result["id"])
            )

            requirement_version_id = (
                latest_versions.get(
                    requirement_id
                )
            )

            if requirement_version_id is None:
                continue

            for finding in result.get(
                "findings",
                [],
            ):
                validation_rows.append(
                    {
                        "requirement_version_id": (
                            requirement_version_id
                        ),
                        "rule_name": (
                            finding.get("rule_name")
                            or "Unknown Rule"
                        ),
                        "passed": bool(
                            finding.get(
                                "passed",
                                False,
                            )
                        ),
                        "message": (
                            finding.get("message")
                            or finding.get(
                                "description",
                                "",
                            )
                        ),
                        "severity": finding.get(
                            "severity"
                        ),
                    }
                )

        # -----------------------------------------------------------
        # Insert all findings in ONE executemany operation.
        # -----------------------------------------------------------

        if validation_rows:
            await self.db.execute(
                text(
                    """
                    INSERT INTO rule_validation
                    (
                        requirement_version_id,
                        rule_name,
                        passed,
                        message,
                        severity
                    )
                    VALUES
                    (
                        :requirement_version_id,
                        :rule_name,
                        :passed,
                        :message,
                        :severity
                    )
                    """
                ),
                validation_rows,
            )

        saved_count = len(validation_rows)

        await self.db.commit()

        return {
            "total": len(results),
            "saved": saved_count,
            "results": results,
        }

    # ---------------------------------------------------------------
    # Versions
    # ---------------------------------------------------------------

    async def create_version(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
        payload: RequirementVersionCreate,
    ) -> RequirementVersionResponse:

        await self._require_project(
            owner_id,
            project_id,
        )

        await self._require_requirement(
            project_id,
            requirement_id,
        )

        await self.repo.lock_requirement_for_versioning(
            requirement_id
        )

        next_number = await self.repo.next_version_number(
            requirement_id
        )

        version = await self.repo.create_version(
            requirement_id=requirement_id,
            version_number=next_number,
            requirement_text=payload.requirement_text,
            change_summary=payload.change_summary,
            created_by=owner_id,
        )

        return RequirementVersionResponse.model_validate(
            version
        )

    async def list_versions(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
    ) -> list[RequirementVersionResponse]:

        await self._require_project(
            owner_id,
            project_id,
        )

        await self._require_requirement(
            project_id,
            requirement_id,
        )

        rows = await self.repo.list_versions(
            requirement_id
        )

        return [
            RequirementVersionResponse.model_validate(row)
            for row in rows
        ]