from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectPermanentDeleteRequest(BaseModel):
    """
    Body of DELETE /api/v1/projects/{project_id}/permanent.

    The API re-checks the typed name server-side so that a direct API call
    cannot permanently delete a project without the same explicit
    confirmation the UI requires.
    """

    confirm_name: str = Field(min_length=1, max_length=200)


CleanupStatus = Literal["completed", "failed", "not_required"]


class StorageCleanupSummary(BaseModel):
    status: CleanupStatus
    total_files: int
    failed_files: int
    correlation_id: UUID


class ProjectPermanentDeleteResponse(BaseModel):
    project_id: UUID
    project_name: str
    deleted_at: datetime
    correlation_id: UUID
    deleted_counts: dict[str, int]
    storage_cleanup: StorageCleanupSummary
    message: str


class StorageCleanupRetryItem(BaseModel):
    correlation_id: UUID
    project_id: UUID
    status: CleanupStatus
    total_files: int
    failed_files: int


class StorageCleanupRetryResponse(BaseModel):
    pending_found: int
    completed: int
    still_failing: int
    items: list[StorageCleanupRetryItem] = Field(default_factory=list)
