from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RepositoryVersionItem(BaseModel):
    """One row of the Versions table."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    is_current: bool
    change_summary: str | None = None
    total_requirements: int
    approved_requirements: int
    pending_requirements: int
    new_count: int
    modified_count: int
    deleted_count: int
    created_at: datetime


class RepositoryVersionSummary(BaseModel):
    """The six summary cards."""

    total_versions: int
    current_version: int | None = None
    previous_version: int | None = None
    approved_requirements: int
    modified_requirements: int
    pending_requirements: int


class RepositoryVersionListResponse(BaseModel):
    summary: RepositoryVersionSummary
    total: int
    page: int
    page_size: int
    items: list[RepositoryVersionItem]


class VersionChangeItem(BaseModel):
    requirement_id: str
    requirement_code: str
    title: str | None = None
    status: str | None = None
    version_number: int | None = None


class VersionChanges(BaseModel):
    new: list[VersionChangeItem] = Field(default_factory=list)
    modified: list[VersionChangeItem] = Field(default_factory=list)
    deleted: list[VersionChangeItem] = Field(default_factory=list)


class VersionRequirement(BaseModel):
    requirement_id: str | None = None
    requirement_code: str
    title: str | None = None
    status: str | None = None


class VersionDocument(BaseModel):
    id: str
    filename: str
    source_type: str | None = None
    size_bytes: int | None = None


class RepositoryVersionDetail(BaseModel):
    """Data for the Version Details drawer."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    version_number: int
    is_current: bool
    change_summary: str | None = None
    created_at: datetime
    created_by_name: str | None = None
    created_by_role: str | None = None

    total_requirements: int
    approved_requirements: int
    pending_requirements: int
    rejected_requirements: int
    new_count: int
    modified_count: int
    deleted_count: int

    is_baseline: bool = False
    changes: VersionChanges
    requirements: list[VersionRequirement] = Field(default_factory=list)
    documents: list[VersionDocument] = Field(default_factory=list)
