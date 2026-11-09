from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.schemas import UserResponse
from core.dependencies import get_current_user
from db.session import get_db
from models.project_deletion import (
    ProjectPermanentDeleteRequest,
    ProjectPermanentDeleteResponse,
    StorageCleanupRetryResponse,
)
from models.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectStatusUpdate,
    ProjectUpdate,
)
from services.project_deletion_service import ProjectDeletionService
from services.project_service import ProjectService

router = APIRouter(prefix="/api/v1/projects", tags=["Projects"])


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    payload: ProjectCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Create a new project owned by the authenticated user."""

    service = ProjectService(db)
    return await service.create_project(UUID(current_user.id), payload)


@router.get(
    "",
    response_model=ProjectListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_projects(
    status_filter: Literal["active", "archived", "suspended"] | None = Query(
        default=None, alias="status"
    ),
    search: str | None = Query(default=None, max_length=200),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectListResponse:
    """
    List projects owned by the authenticated user.

    Supports `?status=active|archived|suspended`, `?search=telecom`,
    and both combined.
    """

    service = ProjectService(db)
    items = await service.list_projects(UUID(current_user.id), status_filter, search)
    return ProjectListResponse(total=len(items), items=items)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
)
async def get_project(
    project_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Get a single project owned by the authenticated user."""

    service = ProjectService(db)
    return await service.get_project(UUID(current_user.id), project_id)


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """
    Update a project. Uses PUT (full-replace) because the "Edit Project"
    form in the UI always submits the complete set of editable fields
    together — there is no partial-field editing surface to justify PATCH.
    """

    service = ProjectService(db)
    return await service.update_project(UUID(current_user.id), project_id, payload)

@router.patch(
    "/{project_id}/status",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
)
async def update_project_status(
    project_id: UUID,
    payload: ProjectStatusUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Change the status of a project."""

    service = ProjectService(db)

    return await service.update_project_status(
        UUID(current_user.id),
        project_id,
        payload.status,
    )

@router.delete(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
)
async def archive_project(
    project_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """
    Archive a project (soft delete). DELETE verb is used for REST
    convention/UI-intent clarity, but this only sets status='archived' —
    the row is never physically deleted (there is no DELETE RLS policy
    on `projects` at all, so a hard delete isn't even possible via RLS).
    """

    service = ProjectService(db)
    return await service.archive_project(UUID(current_user.id), project_id)


@router.delete(
    "/{project_id}/permanent",
    response_model=ProjectPermanentDeleteResponse,
    status_code=status.HTTP_200_OK,
)
async def permanently_delete_project(
    project_id: UUID,
    payload: ProjectPermanentDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectPermanentDeleteResponse:
    """
    Permanently delete a project and ALL of its data (irreversible).

    Separate from the archive endpoint above, which only sets
    status='archived'. The body must carry the exact project name.
    Database deletion is one transaction; storage files are removed
    after it commits (see ProjectDeletionService).
    """

    service = ProjectDeletionService(db)
    return await service.permanently_delete_project(
        UUID(current_user.id), project_id, payload.confirm_name
    )


@router.post(
    "/storage-cleanup/retry",
    response_model=StorageCleanupRetryResponse,
    status_code=status.HTTP_200_OK,
)
async def retry_storage_cleanup(
    correlation_id: UUID | None = Query(default=None),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StorageCleanupRetryResponse:
    """
    Retry storage cleanup for the caller's permanently deleted projects whose
    file removal has not completed. Needs no project row: it works from the
    append-only PROJECT_PERMANENTLY_DELETED / ..._CLEANUP_FAILED events.
    """

    service = ProjectDeletionService(db)
    return await service.retry_storage_cleanup(
        UUID(current_user.id), correlation_id
    )
