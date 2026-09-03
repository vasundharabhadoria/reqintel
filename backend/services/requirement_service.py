from uuid import UUID

from fastapi import HTTPException, UploadFile, status
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

_ALLOWED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx", ".txt": "txt"}
_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}
_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # matches the bucket's file_size_limit


class RequirementService:
    """
    Business logic for Module 2 (Requirements). Every public method takes
    the authenticated user's id and the target project_id; ownership is
    verified via ProjectRepository before any requirement-scoped work
    happens, so a caller can never act on another user's project.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.repo = RequirementRepository(db)
        self.storage = get_storage_client()
        self.extraction_strategy = RuleBasedExtractionStrategy()

    async def _require_project(self, owner_id: UUID, project_id: UUID) -> None:
        project = await self.projects.get_by_id(project_id, owner_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

    async def _require_source(self, project_id: UUID, source_id: UUID) -> dict:
        source = await self.repo.get_source(source_id, project_id)
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requirement source not found.",
            )
        return source

    async def _require_requirement(
        self, project_id: UUID, requirement_id: UUID
    ) -> dict:
        requirement = await self.repo.get_requirement(requirement_id, project_id)
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
        self, owner_id: UUID, project_id: UUID
    ) -> list[RequirementSourceResponse]:
        await self._require_project(owner_id, project_id)
        rows = await self.repo.list_sources(project_id)
        return [RequirementSourceResponse.model_validate(r) for r in rows]

    async def upload_source(
        self, owner_id: UUID, project_id: UUID, file: UploadFile
    ) -> RequirementSourceResponse:
        await self._require_project(owner_id, project_id)

        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file selected.",
            )

        extension = "." + file.filename.rsplit(".", 1)[-1].lower() \
            if "." in file.filename else ""
        source_type = _ALLOWED_EXTENSIONS.get(extension)

        if source_type is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only PDF, DOCX, and TXT files are supported.",
            )

        if file.content_type and file.content_type not in _ALLOWED_MIME_TYPES:
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

        # Create the DB row first to get a stable id for the storage path.
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

        storage_path = f"{project_id}/{source['id']}{extension}"

        try:
            self.storage.storage.from_(REQUIREMENT_SOURCES_BUCKET).upload(
                storage_path,
                file_bytes,
                {"content-type": file.content_type or "application/octet-stream"},
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
            source["id"], project_id, processing_status="uploaded"
        )
        # storage_path has no dedicated setter above; set it via a direct
        # follow-up update so create_source stays a single-purpose insert.
        await self.db.execute(
            __import__("sqlalchemy").text(
                "UPDATE requirement_sources SET storage_path = :p WHERE id = :id"
            ),
            {"p": storage_path, "id": source["id"]},
        )
        updated["storage_path"] = storage_path

        return RequirementSourceResponse.model_validate(updated)

    async def extract_source_text(
        self, owner_id: UUID, project_id: UUID, source_id: UUID
    ) -> RequirementSourceResponse:
        await self._require_project(owner_id, project_id)
        source = await self._require_source(project_id, source_id)

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
            source_id, project_id, processing_status="parsing"
        )

        try:
            file_bytes = self.storage.storage.from_(
                REQUIREMENT_SOURCES_BUCKET
            ).download(source["storage_path"])
        except Exception as exc:
            await self.repo.update_source_processing(
                source_id,
                project_id,
                processing_status="failed",
                extraction_error=f"Could not download stored file: {exc}",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve the stored file.",
            ) from exc

        try:
            extracted_text = extract_text(file_bytes, source["source_type"])
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
                extraction_error="No text could be extracted from the document.",
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
        return RequirementSourceResponse.model_validate(updated)

    # ---------------------------------------------------------------
    # Manual entry
    # ---------------------------------------------------------------

    async def create_manual_requirement(
        self, owner_id: UUID, project_id: UUID, payload: ManualRequirementCreate
    ) -> RequirementResponse:
        await self._require_project(owner_id, project_id)

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

        requirement, _version = await self._create_requirement_with_version(
            project_id=project_id,
            source_id=source["id"],
            title=payload.title,
            requirement_text=payload.requirement_text,
            created_by=owner_id,
        )

        return await self.get_requirement(owner_id, project_id, requirement["id"])

    # ---------------------------------------------------------------
    # Requirement identification
    # ---------------------------------------------------------------

    async def extract_requirements(
        self, owner_id: UUID, project_id: UUID, source_id: UUID
    ) -> ExtractedRequirementSummary:
        await self._require_project(owner_id, project_id)
        source = await self._require_source(project_id, source_id)

        if not source["raw_text"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This source has no extracted text yet. Run text "
                "extraction first.",
            )

        candidate_statements = self.extraction_strategy.identify(
            source["raw_text"]
        )

        created: list[RequirementResponse] = []

        for statement in candidate_statements:
            title = statement[:80] + ("…" if len(statement) > 80 else "")
            requirement, _version = await self._create_requirement_with_version(
                project_id=project_id,
                source_id=source_id,
                title=title,
                requirement_text=statement,
                created_by=owner_id,
            )
            created.append(
                await self.get_requirement(owner_id, project_id, requirement["id"])
            )

        return ExtractedRequirementSummary(
            requirements_created=len(created), items=created
        )

    async def _create_requirement_with_version(
        self,
        project_id: UUID,
        source_id: UUID,
        title: str | None,
        requirement_text: str,
        created_by: UUID,
    ) -> tuple[dict, dict]:
        await self.repo.lock_project_for_code_generation(project_id)
        code = await self.repo.next_requirement_code(project_id)

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
    ) -> RequirementResponse:
        await self._require_project(owner_id, project_id)
        rows = await self.repo.list_requirements(
            project_id, status_filter, search, source_id
        )
        return [RequirementResponse.model_validate(r) for r in rows]

    async def get_requirement(
        self, owner_id: UUID, project_id: UUID, requirement_id: UUID
    ) -> RequirementResponse:
        await self._require_project(owner_id, project_id)
        row = await self._require_requirement(project_id, requirement_id)
        return RequirementResponse.model_validate(row)

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
        await self._require_project(owner_id, project_id)
        await self._require_requirement(project_id, requirement_id)

        await self.repo.lock_requirement_for_versioning(requirement_id)
        next_number = await self.repo.next_version_number(requirement_id)

        version = await self.repo.create_version(
            requirement_id=requirement_id,
            version_number=next_number,
            requirement_text=payload.requirement_text,
            change_summary=payload.change_summary,
            created_by=owner_id,
        )
        return RequirementVersionResponse.model_validate(version)

    async def list_versions(
        self, owner_id: UUID, project_id: UUID, requirement_id: UUID
    ) -> list[RequirementVersionResponse]:
        await self._require_project(owner_id, project_id)
        await self._require_requirement(project_id, requirement_id)

        rows = await self.repo.list_versions(requirement_id)
        return [RequirementVersionResponse.model_validate(r) for r in rows]