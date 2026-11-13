from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

ReportFormat = Literal["pdf", "xlsx", "html"]


class ReportGenerateRequest(BaseModel):
    """
    Payload to generate a report.

    Only the project and the format come from the client. The owner is
    always taken from the authenticated user, and the project is re-checked
    against that owner by the backend before anything is generated.
    """

    project_id: UUID
    report_format: ReportFormat


class ReportResponse(BaseModel):
    """Metadata of one generated report. The storage path is never exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    project_name: str
    generated_by: UUID
    report_format: ReportFormat
    file_name: str
    includes_validation: bool
    includes_ai_suggestions: bool
    includes_quality_scores: bool
    includes_change_impact: bool
    generated_at: datetime


class ReportListResponse(BaseModel):
    """List response for GET /api/v1/reports."""

    total: int
    items: list[ReportResponse]