from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from models.dashboard import (
    DashboardActivity,
    DashboardQuality,
    DashboardSummary,
)
from services.dashboard_repository import DashboardRepository

QUALITY_DIMENSIONS = (
    "clarity",
    "completeness",
    "unambiguity",
    "consistency",
    "specificity",
    "testability",
)

QUALITY_POINTS = {
    "good": 100,
    "needs improvement": 50,
    "poor": 0,
}

# Only events that are actually written to activity_logs.
ACTIVITY_LABELS = {
    "PROJECT_CREATED": "Project created",
    "PROJECT_UPDATED": "Project updated",
    "PROJECT_ARCHIVED": "Project archived",
    "PROJECT_STATUS_CHANGED": "Project status changed",
    "PROJECT_PERMANENTLY_DELETED": "Project permanently deleted",
    "REPORT_GENERATED": "Report generated",
}


def score_quality_assessment(assessment) -> float | None:
    """
    Average of the six dimension points (Good=100, Needs improvement=50,
    Poor=0). Returns None unless ALL six dimensions hold a valid label, so a
    partial or malformed analysis is never counted as a made-up score.
    """

    if not isinstance(assessment, dict):
        return None

    points = []

    for dimension in QUALITY_DIMENSIONS:
        label = assessment.get(dimension)

        if not isinstance(label, str):
            return None

        value = QUALITY_POINTS.get(label.strip().lower())

        if value is None:
            return None

        points.append(value)

    return sum(points) / len(points)


class DashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = DashboardRepository(db)

    async def get_summary(
        self, owner_id: UUID, activity_limit: int = 10
    ) -> DashboardSummary:
        projects = await self.repo.project_counts(owner_id)
        requirements = await self.repo.requirement_counts(owner_id)
        suggestions = await self.repo.suggestion_count(owner_id)

        scores = [
            score
            for score in (
                score_quality_assessment(item)
                for item in await self.repo.latest_quality_assessments(owner_id)
            )
            if score is not None
        ]

        quality = DashboardQuality(
            score=round(sum(scores) / len(scores), 1) if scores else None,
            analysed_requirements=len(scores),
            total_requirements=requirements["total_requirements"],
        )

        rows = await self.repo.recent_activity(
            owner_id, list(ACTIVITY_LABELS), activity_limit
        )

        activity = [
            DashboardActivity(
                id=row["id"],
                action=row["action"],
                label=ACTIVITY_LABELS[row["action"]],
                project_id=(
                    row["entity_id"] if row["entity_type"] == "project" else None
                ),
                project_name=row["project_name"] or row["logged_project_name"],
                detail=(
                    f"{str(row['report_format']).upper()} report"
                    if row["action"] == "REPORT_GENERATED"
                    and row["report_format"]
                    else None
                ),
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return DashboardSummary(
            total_projects=projects["total_projects"],
            active_projects=projects["active_projects"],
            total_requirements=requirements["total_requirements"],
            pending_reviews=requirements["pending_reviews"],
            ai_suggestions_generated=suggestions,
            quality=quality,
            recent_activity=activity,
        )