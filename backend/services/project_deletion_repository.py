import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ACTION_DELETED = "PROJECT_PERMANENTLY_DELETED"
ACTION_CLEANUP_COMPLETED = "PROJECT_STORAGE_CLEANUP_COMPLETED"
ACTION_CLEANUP_FAILED = "PROJECT_STORAGE_CLEANUP_FAILED"


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


class ProjectDeletionRepository:
    """
    Data access for permanent project deletion.

    Deletion order (dictated by the real foreign keys of the live database):

      1. reports               RESTRICT on projects
      2. requirements          RESTRICT on projects; CASCADE removes
                               requirement_versions, rule_validation,
                               ai_analysis, ai_suggestions,
                               requirement_issue_waivers,
                               requirement_traceability,
                               requirement_test_cases and
                               change_impact_analysis
      3. requirement_sources   RESTRICT on projects (requirements must go
                               first: requirements.source_id is RESTRICT)
      4. apis                  RESTRICT on projects
      5. test_cases            RESTRICT on projects
      6. modules               RESTRICT on projects (apis go first)
      7. projects              CASCADE removes repository_versions

    Every statement filters by project_id; the project row itself is
    locked and owner-checked before any of this runs.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------------------------------------------------------------
    # Context / locking / reads
    # ---------------------------------------------------------------

    async def set_rls_context(self, user_id: UUID) -> None:
        """
        Re-establish the RLS user. set_config(..., true) only lasts for the
        current transaction, so it must be repeated after every commit.
        """
        await self.db.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(user_id)},
        )

    async def lock_owned_project(
        self, project_id: UUID, owner_id: UUID
    ) -> dict | None:
        result = await self.db.execute(
            text(
                """
                SELECT id, name, client_name, project_type, status::text AS status
                FROM projects
                WHERE id = :project_id AND owner_id = :owner_id
                FOR UPDATE
                """
            ),
            {"project_id": project_id, "owner_id": owner_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def count_project_data(self, project_id: UUID) -> dict[str, int]:
        """Row counts that will disappear with the project (for the audit event)."""

        result = await self.db.execute(
            text(
                """
                SELECT
                  (SELECT COUNT(*) FROM requirement_sources
                     WHERE project_id = :p)                          AS requirement_sources,
                  (SELECT COUNT(*) FROM requirements
                     WHERE project_id = :p)                          AS requirements,
                  (SELECT COUNT(*) FROM requirement_versions rv
                     JOIN requirements r ON r.id = rv.requirement_id
                     WHERE r.project_id = :p)                        AS requirement_versions,
                  (SELECT COUNT(*) FROM rule_validation v
                     JOIN requirement_versions rv ON rv.id = v.requirement_version_id
                     JOIN requirements r ON r.id = rv.requirement_id
                     WHERE r.project_id = :p)                        AS rule_validations,
                  (SELECT COUNT(*) FROM ai_analysis a
                     JOIN requirement_versions rv ON rv.id = a.requirement_version_id
                     JOIN requirements r ON r.id = rv.requirement_id
                     WHERE r.project_id = :p)                        AS ai_analyses,
                  (SELECT COUNT(*) FROM ai_suggestions s
                     JOIN ai_analysis a ON a.id = s.ai_analysis_id
                     JOIN requirement_versions rv ON rv.id = a.requirement_version_id
                     JOIN requirements r ON r.id = rv.requirement_id
                     WHERE r.project_id = :p)                        AS ai_suggestions,
                  (SELECT COUNT(*) FROM requirement_issue_waivers w
                     JOIN requirement_versions rv ON rv.id = w.requirement_version_id
                     JOIN requirements r ON r.id = rv.requirement_id
                     WHERE r.project_id = :p)                        AS issue_waivers,
                  (SELECT COUNT(*) FROM requirement_traceability t
                     JOIN requirements r ON r.id = t.source_requirement_id
                     WHERE r.project_id = :p)                        AS traceability_links,
                  (SELECT COUNT(*) FROM change_impact_analysis c
                     JOIN requirement_versions rv ON rv.id = c.source_requirement_version_id
                     JOIN requirements r ON r.id = rv.requirement_id
                     WHERE r.project_id = :p)                        AS change_impact_records,
                  (SELECT COUNT(*) FROM repository_versions
                     WHERE project_id = :p)                          AS repository_versions,
                  (SELECT COUNT(*) FROM reports
                     WHERE project_id = :p)                          AS reports,
                  (SELECT COUNT(*) FROM apis WHERE project_id = :p)  AS apis,
                  (SELECT COUNT(*) FROM test_cases
                     WHERE project_id = :p)                          AS test_cases,
                  (SELECT COUNT(*) FROM modules
                     WHERE project_id = :p)                          AS modules
                """
            ),
            {"p": project_id},
        )
        return {k: int(v) for k, v in dict(result.mappings().one()).items()}

    async def collect_storage_paths(self, project_id: UUID) -> dict[str, list[str]]:
        """Paths recorded in the database, per bucket."""

        sources = await self.db.execute(
            text(
                """
                SELECT storage_path FROM requirement_sources
                WHERE project_id = :p AND storage_path IS NOT NULL
                """
            ),
            {"p": project_id},
        )
        reports = await self.db.execute(
            text(
                """
                SELECT file_path FROM reports
                WHERE project_id = :p AND file_path IS NOT NULL
                """
            ),
            {"p": project_id},
        )

        return {
            "requirement_sources": [r[0] for r in sources.all()],
            "reports": [r[0] for r in reports.all()],
        }

    # ---------------------------------------------------------------
    # Deletes. Each returns the number of rows removed so the service can
    # detect a silent no-op (e.g. a missing DELETE policy under RLS).
    # ---------------------------------------------------------------

    async def _delete(self, sql: str, project_id: UUID) -> int:
        result = await self.db.execute(text(sql), {"p": project_id})
        return int(result.rowcount or 0)

    async def delete_reports(self, project_id: UUID) -> int:
        return await self._delete("DELETE FROM reports WHERE project_id = :p", project_id)

    async def delete_requirements(self, project_id: UUID) -> int:
        return await self._delete(
            "DELETE FROM requirements WHERE project_id = :p", project_id
        )

    async def delete_requirement_sources(self, project_id: UUID) -> int:
        return await self._delete(
            "DELETE FROM requirement_sources WHERE project_id = :p", project_id
        )

    async def delete_apis(self, project_id: UUID) -> int:
        return await self._delete("DELETE FROM apis WHERE project_id = :p", project_id)

    async def delete_test_cases(self, project_id: UUID) -> int:
        return await self._delete(
            "DELETE FROM test_cases WHERE project_id = :p", project_id
        )

    async def delete_modules(self, project_id: UUID) -> int:
        return await self._delete(
            "DELETE FROM modules WHERE project_id = :p", project_id
        )

    async def delete_project(self, project_id: UUID, owner_id: UUID) -> int:
        result = await self.db.execute(
            text("DELETE FROM projects WHERE id = :p AND owner_id = :o"),
            {"p": project_id, "o": owner_id},
        )
        return int(result.rowcount or 0)

    # ---------------------------------------------------------------
    # Append-only audit events
    # ---------------------------------------------------------------

    async def log_event(
        self,
        user_id: UUID,
        action: str,
        project_id: UUID,
        details: dict,
    ) -> None:
        await self.db.execute(
            text(
                """
                INSERT INTO activity_logs
                    (user_id, action, entity_type, entity_id, details)
                VALUES
                    (:user_id, :action, 'project', :entity_id,
                     CAST(:details AS jsonb))
                """
            ),
            {
                "user_id": user_id,
                "action": action,
                "entity_id": project_id,
                "details": json.dumps(details, default=str),
            },
        )

    async def list_pending_cleanups(
        self, user_id: UUID, correlation_id: UUID | None = None
    ) -> list[dict]:
        """
        Deletion events that still have files to clean up: they listed
        storage objects and no COMPLETED event exists for their
        correlation id. Reads only activity_logs, so it works after the
        project row is gone.
        """

        sql = """
            SELECT
                d.entity_id AS project_id,
                d.details   AS details,
                (
                    SELECT f.details
                    FROM activity_logs f
                    WHERE f.user_id = d.user_id
                      AND f.action = :failed
                      AND f.details ->> 'correlation_id'
                          = d.details ->> 'correlation_id'
                    ORDER BY f.created_at DESC
                    LIMIT 1
                ) AS last_failed
            FROM activity_logs d
            WHERE d.user_id = :user_id
              AND d.action = :deleted
              AND jsonb_typeof(d.details -> 'storage_objects') = 'array'
              AND jsonb_array_length(d.details -> 'storage_objects') > 0
              AND NOT EXISTS (
                    SELECT 1
                    FROM activity_logs c
                    WHERE c.user_id = d.user_id
                      AND c.action = :completed
                      AND c.details ->> 'correlation_id'
                          = d.details ->> 'correlation_id'
              )
        """
        params: dict = {
            "user_id": user_id,
            "deleted": ACTION_DELETED,
            "failed": ACTION_CLEANUP_FAILED,
            "completed": ACTION_CLEANUP_COMPLETED,
        }

        if correlation_id is not None:
            sql += " AND d.details ->> 'correlation_id' = :cid"
            params["cid"] = str(correlation_id)

        sql += " ORDER BY d.created_at ASC"

        result = await self.db.execute(text(sql), params)

        rows = []
        for row in result.mappings().all():
            details = _as_json(row["details"], {})
            last_failed = _as_json(row["last_failed"], None)
            rows.append(
                {
                    "project_id": row["project_id"],
                    "details": details,
                    "last_failed": last_failed,
                }
            )

        return rows
