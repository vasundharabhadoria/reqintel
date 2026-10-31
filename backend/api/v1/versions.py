from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.schemas import UserResponse
from core.dependencies import get_current_user
from db.session import get_db
from models.repository_version import (
    RepositoryVersionDetail,
    RepositoryVersionListResponse,
)
from services.version_service import VersionService


router = APIRouter(
    prefix="/api/v1/projects/{project_id}/versions",
    tags=["Repository Versions"],
)


@router.get("", response_model=RepositoryVersionListResponse)
async def list_repository_versions(
    project_id: UUID,
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepositoryVersionListResponse:
    """Versions table + the six summary cards."""

    return await VersionService(db).list_versions(
        UUID(current_user.id), project_id, search, page, page_size
    )


@router.get("/{version_id}", response_model=RepositoryVersionDetail)
async def get_repository_version(
    project_id: UUID,
    version_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepositoryVersionDetail:
    """Data for the Version Details drawer."""

    return await VersionService(db).get_version(
        UUID(current_user.id), project_id, version_id
    )
