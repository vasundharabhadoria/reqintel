from uuid import UUID
from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
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
    TraceabilityLinkCreate,
    TraceabilityLinkListResponse,
    TraceabilityLinkResponse,
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
    service = RequirementService(db)

    try:
        return await service.extract_requirements(
            UUID(current_user.id),
            project_id,
            source_id,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
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


@router.get("/analysis")
async def get_saved_project_analysis(
    project_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    return await service.get_saved_project_analysis(
        UUID(current_user.id),
        project_id,
    )


@router.post(
    "/{requirement_id}/approve",
)
async def approve_requirement(
    project_id: UUID,
    requirement_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    return await service.approve_requirement(
        UUID(current_user.id),
        project_id,
        requirement_id,
    )


@router.post(
    "/{requirement_id}/reject",
)
async def reject_requirement(
    project_id: UUID,
    requirement_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    return await service.reject_requirement(
        UUID(current_user.id),
        project_id,
        requirement_id,
    )


class IssueWaiverRequest(BaseModel):
    rule_name: str
    reason: str | None = None


@router.post(
    "/{requirement_id}/waivers",
)
async def waive_issue(
    project_id: UUID,
    requirement_id: UUID,
    payload: IssueWaiverRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    return await service.set_issue_waiver(
        UUID(current_user.id),
        project_id,
        requirement_id,
        payload.rule_name,
        True,
        payload.reason,
    )


@router.delete(
    "/{requirement_id}/waivers",
)
async def remove_issue_waiver(
    project_id: UUID,
    requirement_id: UUID,
    rule_name: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    return await service.set_issue_waiver(
        UUID(current_user.id),
        project_id,
        requirement_id,
        rule_name,
        False,
    )


@router.post(
    "/{requirement_id}/suggestions/{suggestion_id}/accept",
)
async def accept_suggestion(
    project_id: UUID,
    requirement_id: UUID,
    suggestion_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    return await service.accept_ai_suggestion(
        UUID(current_user.id),
        project_id,
        requirement_id,
        suggestion_id,
    )


@router.post(
    "/{requirement_id}/suggestions/{suggestion_id}/reject",
)
async def reject_suggestion(
    project_id: UUID,
    requirement_id: UUID,
    suggestion_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    return await service.reject_ai_suggestion(
        UUID(current_user.id),
        project_id,
        requirement_id,
        suggestion_id,
    )

@router.get(
    "/traceability",
    response_model=TraceabilityLinkListResponse,
)
async def list_project_traceability_links(
    project_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TraceabilityLinkListResponse:
    service = RequirementService(db)

    items = await service.list_project_traceability_links(
        UUID(current_user.id),
        project_id,
    )

    validated_items = [
        TraceabilityLinkResponse.model_validate(item)
        for item in items
    ]

    return TraceabilityLinkListResponse(
        total=len(validated_items),
        items=validated_items,
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

@router.post(
    "/{requirement_id}/traceability",
    response_model=TraceabilityLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_traceability_link(
    project_id: UUID,
    requirement_id: UUID,
    payload: TraceabilityLinkCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TraceabilityLinkResponse:
    service = RequirementService(db)

    try:
        result = await service.create_traceability_link(
            UUID(current_user.id),
            project_id,
            requirement_id,
            payload.target_requirement_id,
            payload.link_type,
        )
        return TraceabilityLinkResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
@router.get(
    "/traceability/suggestions",
)
async def suggest_traceability_links(
    project_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    suggestions = await service.suggest_traceability_links(
        UUID(current_user.id),
        project_id,
    )

    return {
        "total": len(suggestions),
        "items": suggestions,
    }


@router.get(
    "/{requirement_id}/traceability",
    response_model=TraceabilityLinkListResponse,
)
async def list_traceability_links(
    project_id: UUID,
    requirement_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TraceabilityLinkListResponse:
    service = RequirementService(db)

    items = await service.list_traceability_links(
        UUID(current_user.id),
        project_id,
        requirement_id,
    )

    validated_items = [
        TraceabilityLinkResponse.model_validate(item)
        for item in items
    ]

    return TraceabilityLinkListResponse(
        total=len(validated_items),
        items=validated_items,
    )
@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_source(
    project_id: UUID,
    source_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = RequirementService(db)

    await service.delete_source(
        user_id=UUID(current_user.id),
        project_id=project_id,
        source_id=source_id,
    )