from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ProjectStatus = Literal["active", "archived", "suspended"]


class ProjectCreate(BaseModel):
    """Payload to create a project. owner_id is never accepted from the
    client — it is always taken from the authenticated user."""

    name: str = Field(min_length=1, max_length=200, examples=["Telecom Billing System"])
    client_name: str | None = Field(default=None, max_length=200, examples=["Quantum Telecom Inc."])
    project_type: str | None = Field(default=None, max_length=100, examples=["Telecom"])
    description: str | None = Field(default=None, examples=["Modernize legacy billing system."])


class ProjectUpdate(BaseModel):
    """Full-replace payload for editing a project (used with PUT)."""

    name: str = Field(min_length=1, max_length=200, examples=["Telecom Billing System"])
    client_name: str | None = Field(default=None, max_length=200, examples=["Quantum Telecom Inc."])
    project_type: str | None = Field(default=None, max_length=100, examples=["Telecom"])
    description: str | None = Field(default=None, examples=["Modernize legacy billing system."])

class ProjectStatusUpdate(BaseModel):
    """Payload for changing a project's status."""

    status: ProjectStatus

class ProjectResponse(BaseModel):
    """A single project as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    client_name: str | None
    project_type: str | None
    description: str | None
    status: ProjectStatus
    owner_id: UUID
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    """List response for GET /api/v1/projects."""

    total: int
    items: list[ProjectResponse]