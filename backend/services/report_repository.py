import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_REPORT_SELECT = """
    r.id,
    r.project_id,
    p.name                              AS project_name,
    r.generated_by,
    CAST(r.report_format AS text)       AS report_format,
    r.includes_validation,
    r.includes_ai_suggestions,
    r.includes_quality_scores,
    r.includes_change_impact,
    r.file_path,
    r.generated_at
"""


class ReportRepository:
    """
    Data access for the `reports` table and the read-only queries that feed
    report content.

    Every query is scoped to projects owned by `owner_id` explicitly
    (defense in depth) in addition to RLS: a row that belongs to someone
    else is simply not found, and callers turn that into a 404.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------------------------------------------------------------
    # Report metadata
    # ---------------------------------------------------------------

    async def insert_report(
        self,
        report_id: UUID,
        project_id: UUID,
        owner_id: UUID,
        report_format: str,
        file_path: str,
        generated_at: datetime,
        includes_validation: bool,
        includes_ai_suggestions: bool,
        includes_quality_scores: bool,
        includes_change_impact: bool,
    ) -> dict | None:
        """
        Insert one report row. The row is only inserted when the project is
        owned by `owner_id`; otherwise nothing is inserted and None is
        returned.
        """

        result = await self.db.execute(
            text(
                f"""
                WITH inserted AS (
                    INSERT INTO reports (
                        id, project_id, generated_by, report_format,
                        includes_validation, includes_ai_suggestions,
                        includes_quality_scores, includes_change_impact,
                        file_path, generated_at
                    )
                    SELECT
                        CAST(:report_id AS uuid),
                        p.id,
                        CAST(:owner_id AS uuid),
                        CAST(:report_format AS report_format_enum),
                        :includes_validation,
                        :includes_ai_suggestions,
                        :includes_quality_scores,
                        :includes_change_impact,
                        :file_path,
                        CAST(:generated_at AS timestamptz)
                    FROM projects p
                    WHERE p.id = CAST(:project_id AS uuid)
                      AND p.owner_id = CAST(:owner_id AS uuid)
                    RETURNING *
                )
                SELECT {_REPORT_SELECT}
                FROM inserted r
                JOIN projects p ON p.id = r.project_id
                """
            ),
            {
                "report_id": str(report_id),
                "project_id": str(project_id),
                "owner_id": str(owner_id),
                "report_format": report_format,
                "file_path": file_path,
                "generated_at": generated_at,
                "includes_validation": includes_validation,
                "includes_ai_suggestions": includes_ai_suggestions,
                "includes_quality_scores": includes_quality_scores,
                "includes_change_impact": includes_change_impact,
            },
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_for_owner(
        self, report_id: UUID, owner_id: UUID
    ) -> dict | None:
        result = await self.db.execute(
            text(
                f"""
                SELECT {_REPORT_SELECT}
                FROM reports r
                JOIN projects p ON p.id = r.project_id
                WHERE r.id = :report_id
                  AND p.owner_id = :owner_id
                """
            ),
            {"report_id": report_id, "owner_id": owner_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def list_for_owner(
        self,
        owner_id: UUID,
        project_id: UUID | None,
        report_format: str | None,
        limit: int,
    ) -> list[dict]:
        query = f"""
            SELECT {_REPORT_SELECT}
            FROM reports r
            JOIN projects p ON p.id = r.project_id
            WHERE p.owner_id = :owner_id
        """
        params: dict = {"owner_id": owner_id, "limit": limit}

        if project_id is not None:
            query += " AND r.project_id = :project_id"
            params["project_id"] = project_id

        if report_format is not None:
            query += (
                " AND r.report_format = CAST(:report_format AS report_format_enum)"
            )
            params["report_format"] = report_format

        query += " ORDER BY r.generated_at DESC, r.id DESC LIMIT :limit"

        result = await self.db.execute(text(query), params)
        return [dict(row) for row in result.mappings().all()]

    async def delete_for_owner(
        self, report_id: UUID, owner_id: UUID
    ) -> dict | None:
        """
        Delete one report row owned by `owner_id`. Returns the deleted row
        (with its storage path) or None when nothing was deleted.
        """

        result = await self.db.execute(
            text(
                """
                DELETE FROM reports r
                USING projects p
                WHERE r.id = :report_id
                  AND p.id = r.project_id
                  AND p.owner_id = :owner_id
                RETURNING
                    r.id,
                    r.project_id,
                    p.name AS project_name,
                    CAST(r.report_format AS text) AS report_format,
                    r.file_path
                """
            ),
            {"report_id": report_id, "owner_id": owner_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    # ---------------------------------------------------------------
    # Activity log
    # ---------------------------------------------------------------

    async def log_activity(
        self,
        user_id: UUID,
        action: str,
        report_id: UUID,
        details: dict,
    ) -> None:
        await self.db.execute(
            text(
                """
                INSERT INTO activity_logs
                    (user_id, action, entity_type, entity_id, details)
                VALUES
                    (:user_id, :action, 'report', :entity_id,
                     CAST(:details AS jsonb))
                """
            ),
            {
                "user_id": user_id,
                "action": action,
                "entity_id": report_id,
                "details": json.dumps(details, default=str),
            },
        )

    # ---------------------------------------------------------------
    # Report content (read-only)
    # ---------------------------------------------------------------

    async def fetch_requirements(
        self, project_id: UUID, owner_id: UUID
    ) -> list[dict]:
        """
        One row per requirement of the project: its CURRENT version (highest
        version_number) and the latest quality analysis of that version.
        Nothing is invented: a requirement with no analysis simply has NULL
        analysis columns.
        """

        result = await self.db.execute(
            text(
                """
                SELECT
                    r.id,
                    r.requirement_code,
                    r.title,
                    CAST(r.status AS text)  AS status,
                    r.created_at,
                    r.updated_at,
                    cv.version_number,
                    cv.requirement_text,
                    cv.change_summary,
                    (
                        SELECT COUNT(*)
                        FROM requirement_versions v
                        WHERE v.requirement_id = r.id
                    )                       AS version_count,
                    aa.id                   AS ai_analysis_id,
                    aa.model_name,
                    aa.analysis_summary,
                    aa.recommendations,
                    aa.ambiguity_detected,
                    aa.created_at           AS analysed_at,
                    aa.raw_response_json -> 'quality_assessment'
                                            AS quality_assessment
                FROM requirements r
                JOIN projects p
                  ON p.id = r.project_id
                 AND p.owner_id = :owner_id
                LEFT JOIN LATERAL (
                    SELECT v.id, v.version_number, v.requirement_text,
                           v.change_summary
                    FROM requirement_versions v
                    WHERE v.requirement_id = r.id
                    ORDER BY v.version_number DESC, v.created_at DESC
                    LIMIT 1
                ) cv ON TRUE
                LEFT JOIN LATERAL (
                    SELECT a.id, a.model_name, a.analysis_summary,
                           a.recommendations, a.ambiguity_detected,
                           a.created_at, a.raw_response_json
                    FROM ai_analysis a
                    WHERE a.requirement_version_id = cv.id
                      AND a.prompt_type = 'requirement_quality_analysis'
                    ORDER BY a.created_at DESC, a.id DESC
                    LIMIT 1
                ) aa ON TRUE
                WHERE r.project_id = :project_id
                ORDER BY r.requirement_code ASC, r.id ASC
                """
            ),
            {"project_id": project_id, "owner_id": owner_id},
        )
        return [dict(row) for row in result.mappings().all()]

    async def fetch_suggestions(
        self, analysis_ids: list[UUID]
    ) -> list[dict]:
        """AI suggestions of the given analyses (already project-scoped)."""

        if not analysis_ids:
            return []

        result = await self.db.execute(
            text(
                """
                SELECT
                    s.ai_analysis_id,
                    CAST(s.suggestion_type AS text) AS suggestion_type,
                    CAST(s.status AS text)          AS status,
                    s.suggestion_text
                FROM ai_suggestions s
                WHERE s.ai_analysis_id = ANY(CAST(:ids AS uuid[]))
                ORDER BY s.created_at ASC, s.id ASC
                """
            ),
            {"ids": [str(i) for i in analysis_ids]},
        )
        return [dict(row) for row in result.mappings().all()]