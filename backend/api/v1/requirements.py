from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.schemas import UserResponse
from core.dependencies import get_current_user
from db.session import get_db
from models.requirement import (
    ExtractedRequirementSummary,
    ManualRequirementCreate,
    RequirementListResponse,
    RequirementResponse,
    RequirementSourceListResponse,
    RequirementSourceResponse,
    RequirementStatus,
    RequirementVersionCreate,
    RequirementVersionListResponse,
    RequirementVersionResponse,
)
from services.requirement_service import RequirementService


router = APIRouter(
    prefix="/api/v1/projects/{project_id}/requirements",
    tags=["Requirements"],
)


@router.get(
    "/sources",
    response_model=RequirementSourceListResponse,
)
async def list_sources(
    project_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequirementSourceListResponse:
    service = RequirementService(db)

    items = await service.list_sources(
        UUID(current_user.id),
        project_id,
    )

    return RequirementSourceListResponse(
        total=len(items),
        items=items,
    )


@router.get("/sources/{source_id}/file")
async def get_source_file(
    project_id: UUID,
    source_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    return await service.get_source_file(
        UUID(current_user.id),
        project_id,
        source_id,
    )


@router.post(
    "/sources/upload",
    response_model=RequirementSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_source(
    project_id: UUID,
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequirementSourceResponse:
    """Upload a PDF/DOCX/TXT requirement source document."""

    service = RequirementService(db)

    return await service.upload_source(
        UUID(current_user.id),
        project_id,
        file,
    )


@router.post(
    "/sources/manual",
    response_model=RequirementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_requirement(
    project_id: UUID,
    payload: ManualRequirementCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequirementResponse:
    """Create a requirement manually, without document extraction."""

    service = RequirementService(db)

    return await service.create_manual_requirement(
        UUID(current_user.id),
        project_id,
        payload,
    )


@router.post(
    "/sources/{source_id}/extract",
    response_model=RequirementSourceResponse,
)
async def extract_source_text(
    project_id: UUID,
    source_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequirementSourceResponse:
    """Extract raw text from an uploaded document source."""

    service = RequirementService(db)

    return await service.extract_source_text(
        UUID(current_user.id),
        project_id,
        source_id,
    )


@router.post(
    "/sources/{source_id}/extract-requirements",
    response_model=ExtractedRequirementSummary,
    status_code=status.HTTP_201_CREATED,
)
async def extract_requirements(
    project_id: UUID,
    source_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExtractedRequirementSummary:
    """Run rule-based requirement identification."""

    service = RequirementService(db)

    return await service.extract_requirements(
        UUID(current_user.id),
        project_id,
        source_id,
    )


@router.get(
    "",
    response_model=RequirementListResponse,
)
async def list_requirements(
    project_id: UUID,
    status_filter: RequirementStatus | None = Query(
        default=None,
        alias="status",
    ),
    search: str | None = Query(
        default=None,
        max_length=200,
    ),
    source_id: UUID | None = Query(default=None),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequirementListResponse:
    service = RequirementService(db)

    items = await service.list_requirements(
        UUID(current_user.id),
        project_id,
        status_filter,
        search,
        source_id,
    )

    return RequirementListResponse(
        total=len(items),
        items=items,
    )


@router.post("/analyze")
async def analyze_project_requirements(
    project_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    return await service.analyze_project_requirements(
        UUID(current_user.id),
        project_id,
    )


@router.get(
    "/{requirement_id}",
    response_model=RequirementResponse,
)
async def get_requirement(
    project_id: UUID,
    requirement_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequirementResponse:
    service = RequirementService(db)

    return await service.get_requirement(
        UUID(current_user.id),
        project_id,
        requirement_id,
    )


@router.post(
    "/{requirement_id}/versions",
    response_model=RequirementVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    project_id: UUID,
    requirement_id: UUID,
    payload: RequirementVersionCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequirementVersionResponse:
    service = RequirementService(db)

    return await service.create_version(
        UUID(current_user.id),
        project_id,
        requirement_id,
        payload,
    )


@router.get(
    "/{requirement_id}/versions",
    response_model=RequirementVersionListResponse,
)
async def list_versions(
    project_id: UUID,
    requirement_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequirementVersionListResponse:
    service = RequirementService(db)

    items = await service.list_versions(
        UUID(current_user.id),
        project_id,
        requirement_id,
    )

    return RequirementVersionListResponse(
        total=len(items),
        items=items,
    )
@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    project_id: UUID,
    source_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    await service.delete_source(
        user_id=UUID(current_user.id),
        project_id=project_id,
        source_id=source_id,
    )

    return None