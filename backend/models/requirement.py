from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal["docx", "pdf", "txt", "manual", "email"]
ProcessingStatus = Literal["uploaded", "parsing", "completed", "failed"]
RequirementStatus = Literal["pending", "approved", "rejected", "deprecated"]


class RequirementSourceResponse(BaseModel):
    """A single requirement_sources row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    source_type: SourceType
    original_filename: str | None
    file_size_bytes: int | None
    mime_type: str | None
    processing_status: ProcessingStatus
    extraction_error: str | None
    uploaded_by: UUID
    uploaded_at: datetime
    # raw_text is intentionally omitted from the list/summary shape; it can
    # be large. Exposed only where a caller explicitly needs full text.


class RequirementSourceListResponse(BaseModel):
    total: int
    items: list[RequirementSourceResponse]


class ManualRequirementCreate(BaseModel):
    """Payload for creating a requirement without document extraction."""

    title: str = Field(min_length=1, max_length=255)
    requirement_text: str = Field(min_length=1)


class RequirementVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requirement_id: UUID
    version_number: int
    requirement_text: str
    change_summary: str | None
    final_quality_score: float | None
    created_by: UUID
    created_at: datetime


class RequirementVersionListResponse(BaseModel):
    total: int
    items: list[RequirementVersionResponse]


class RequirementVersionCreate(BaseModel):
    requirement_text: str = Field(min_length=1)
    change_summary: str | None = Field(default=None, max_length=500)


class RequirementResponse(BaseModel):
    """A requirement plus its resolved current version (if any)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    source_id: UUID
    requirement_code: str
    title: str | None
    status: RequirementStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    current_version_number: int | None = None
    current_requirement_text: str | None = None


class RequirementListResponse(BaseModel):
    total: int
    items: list[RequirementResponse]


class ExtractedRequirementSummary(BaseModel):
    """Returned by the extract-requirements endpoint."""

    requirements_created: int
    items: list[RequirementResponse]
    is_srs: bool = True