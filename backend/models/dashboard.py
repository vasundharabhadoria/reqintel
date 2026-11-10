from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DashboardQuality(BaseModel):
    """Overall requirement quality. `score` is None when nothing is analysed."""

    score: float | None
    analysed_requirements: int
    total_requirements: int


class DashboardActivity(BaseModel):
    id: UUID
    action: str
    label: str
    project_id: UUID | None = None
    project_name: str | None = None
    detail: str | None = None
    created_at: datetime


class DashboardSummary(BaseModel):
    total_projects: int
    active_projects: int
    total_requirements: int
    pending_reviews: int
    ai_suggestions_generated: int
    quality: DashboardQuality
    recent_activity: list[DashboardActivity]