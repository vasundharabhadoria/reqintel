import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _as_json(value, default):
    """asyncpg returns jsonb from text() queries as a string."""
    if value is None:
        return default

    if isinstance(value, (list, dict)):
        return value

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class DashboardRepository:
    """
    Read-only queries for the dashboard.

    Every query is scoped to the projects owned by `owner_id` (and, for the
    activity feed, to that user's own log rows), independent of RLS.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def project_counts(self, owner_id: UUID) -> dict[str, int]:
        result = await self.db.execute(
            text(
                """
                SELECT
                    COUNT(*)                                   AS total_projects,
                    COUNT(*) FILTER (WHERE status = 'active')  AS active_projects
                FROM projects
                WHERE owner_id = :owner_id
                """
            ),
            {"owner_id": owner_id},
        )
        return {k: int(v) for k, v in result.mappings().one().items()}

    async def requirement_counts(self, owner_id: UUID) -> dict[str, int]:
        result = await self.db.execute(
            text(
                """
                SELECT
                    COUNT(*)                                       AS total_requirements,
                    COUNT(*) FILTER (WHERE r.status = 'pending')   AS pending_reviews
                FROM requirements r
                JOIN projects p ON p.id = r.project_id
                WHERE p.owner_id = :owner_id
                """
            ),
            {"owner_id": owner_id},
        )
        return {k: int(v) for k, v in result.mappings().one().items()}

    async def suggestion_count(self, owner_id: UUID) -> int:
        result = await self.db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM ai_suggestions s
                JOIN ai_analysis a            ON a.id  = s.ai_analysis_id
                JOIN requirement_versions rv  ON rv.id = a.requirement_version_id
                JOIN requirements r           ON r.id  = rv.requirement_id
                JOIN projects p               ON p.id  = r.project_id
                WHERE p.owner_id = :owner_id
                """
            ),
            {"owner_id": owner_id},
        )
        return int(result.scalar_one())

    async def latest_quality_assessments(self, owner_id: UUID) -> list[dict]:
        """
        One row per requirement that has an AI analysis on its CURRENT
        version (highest version_number): the latest quality-analysis row for
        that version. Older versions never contribute.
        """

        result = await self.db.execute(
            text(
                """
                WITH current_versions AS (
                    SELECT DISTINCT ON (rv.requirement_id)
                           rv.id AS version_id
                    FROM requirement_versions rv
                    JOIN requirements r ON r.id = rv.requirement_id
                    JOIN projects p     ON p.id = r.project_id
                    WHERE p.owner_id = :owner_id
                    ORDER BY rv.requirement_id, rv.version_number DESC
                )
                SELECT DISTINCT ON (a.requirement_version_id)
                       a.raw_response_json -> 'quality_assessment'
                           AS quality_assessment
                FROM ai_analysis a
                JOIN current_versions cv
                  ON cv.version_id = a.requirement_version_id
                WHERE a.prompt_type = 'requirement_quality_analysis'
                ORDER BY a.requirement_version_id,
                         a.created_at DESC,
                         a.id DESC
                """
            ),
            {"owner_id": owner_id},
        )

        return [
            _as_json(row["quality_assessment"], None)
            for row in result.mappings().all()
        ]

    async def recent_activity(
        self, owner_id: UUID, actions: list[str], limit: int
    ) -> list[dict]:
        result = await self.db.execute(
            text(
                """
                SELECT
                    al.id,
                    al.action,
                    al.entity_type,
                    al.entity_id,
                    al.created_at,
                    p.name                          AS project_name,
                    al.details ->> 'project_name'   AS logged_project_name,
                    al.details ->> 'report_format'  AS report_format
                FROM activity_logs al
                LEFT JOIN projects p
                       ON al.entity_type = 'project'
                      AND p.id = al.entity_id
                      AND p.owner_id = :owner_id
                WHERE al.user_id = :owner_id
                  AND al.action = ANY(CAST(:actions AS text[]))
                ORDER BY al.created_at DESC, al.id DESC
                LIMIT :limit
                """
            ),
            {"owner_id": owner_id, "actions": actions, "limit": limit},
        )
        return [dict(row) for row in result.mappings().all()]