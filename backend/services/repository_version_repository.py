import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_LIST_COLUMNS = (
    "id, project_id, version_number, is_current, change_summary, "
    "total_requirements, approved_requirements, pending_requirements, "
    "rejected_requirements, new_count, modified_count, deleted_count, "
    "created_at"
)

_LIST_COLUMNS_QUALIFIED = ", ".join(
    f"rv.{column.strip()}" for column in _LIST_COLUMNS.split(",")
)


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


class RepositoryVersionRepository:
    """
    Data access for `repository_versions`.

    A repository version is a project-level snapshot created after a
    successful requirement analysis. It is compared with the previous
    snapshot to find what is new, modified and deleted.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------------------------------------------------------------
    # Create snapshot
    # ---------------------------------------------------------------

    async def _lock_project(self, project_id: UUID) -> None:
        # Salt 2: separate from code generation (0) and requirement
        # version numbers (1). Released automatically at COMMIT/ROLLBACK.
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 2))"),
            {"key": str(project_id)},
        )

    async def _load_current_requirements(
        self,
        project_id: UUID,
    ) -> list[dict]:
        result = await self.db.execute(
            text(
                """
                SELECT
                    r.id AS requirement_id,
                    r.requirement_code,
                    COALESCE(
                        NULLIF(BTRIM(r.title), ''),
                        LEFT(v.requirement_text, 120)
                    ) AS title,
                    r.status::text AS status,
                    v.version_id AS requirement_version_id,
                    v.version_number
                FROM requirements r
                LEFT JOIN v_requirement_current_version v
                    ON v.requirement_id = r.id
                WHERE r.project_id = :project_id
                ORDER BY r.requirement_code ASC
                """
            ),
            {"project_id": project_id},
        )

        return [
            {
                "requirement_id": str(row["requirement_id"]),
                "requirement_version_id": (
                    str(row["requirement_version_id"])
                    if row["requirement_version_id"]
                    else None
                ),
                "requirement_code": row["requirement_code"],
                "title": row["title"],
                "status": row["status"],
                "version_number": row["version_number"],
            }
            for row in result.mappings().all()
        ]

    async def _load_documents(self, project_id: UUID) -> list[dict]:
        result = await self.db.execute(
            text(
                """
                SELECT
                    id,
                    original_filename,
                    source_type::text AS source_type,
                    file_size_bytes
                FROM requirement_sources
                WHERE project_id = :project_id
                ORDER BY uploaded_at ASC
                """
            ),
            {"project_id": project_id},
        )

        return [
            {
                "id": str(row["id"]),
                "filename": row["original_filename"] or "Manual requirements",
                "source_type": row["source_type"],
                "size_bytes": row["file_size_bytes"],
            }
            for row in result.mappings().all()
        ]

    @staticmethod
    def _build_summary(is_first: bool, new, modified, deleted) -> str:
        if is_first:
            return "Initial Repository"

        parts = []

        if new:
            parts.append(f"{len(new)} new")
        if modified:
            parts.append(f"{len(modified)} modified")
        if deleted:
            parts.append(f"{len(deleted)} deleted")

        return ", ".join(parts) if parts else "Review status updated"

    async def create_snapshot(
        self,
        project_id: UUID,
        created_by: UUID | None,
    ) -> dict | None:
        """
        Create the next repository version, or return None when nothing
        changed since the latest version.

        - First snapshot of a project is V1 ("Initial Repository").
        - NEW       requirement id not in the previous snapshot.
        - MODIFIED  same requirement id, different requirement version.
        - DELETED   in the previous snapshot, gone from the project.
        - A review-status-only change (approved/pending/...) also creates
          a version, with 0 new / 0 modified / 0 deleted.
        - Calling it twice with no changes creates one version only.
        """

        await self._lock_project(project_id)

        current_items = await self._load_current_requirements(project_id)

        previous_result = await self.db.execute(
            text(
                """
                SELECT id, version_number, snapshot
                FROM repository_versions
                WHERE project_id = :project_id
                ORDER BY version_number DESC
                LIMIT 1
                """
            ),
            {"project_id": project_id},
        )
        previous = previous_result.mappings().first()

        previous_items = _as_json(previous["snapshot"], []) if previous else []

        if previous is None and not current_items:
            return None

        previous_map = {i["requirement_id"]: i for i in previous_items}
        current_map = {i["requirement_id"]: i for i in current_items}

        new_items = [
            item for key, item in current_map.items()
            if key not in previous_map
        ]

        modified_items = [
            item for key, item in current_map.items()
            if key in previous_map
            and previous_map[key].get("requirement_version_id")
            != item.get("requirement_version_id")
        ]

        deleted_items = [
            item for key, item in previous_map.items()
            if key not in current_map
        ]

        status_changed = any(
            key in previous_map
            and previous_map[key].get("requirement_version_id")
            == item.get("requirement_version_id")
            and previous_map[key].get("status") != item.get("status")
            for key, item in current_map.items()
        )

        if (
            previous is not None
            and not new_items
            and not modified_items
            and not deleted_items
            and not status_changed
        ):
            return None

        version_number = int(previous["version_number"]) + 1 if previous else 1

        statuses = [str(i.get("status") or "") for i in current_items]
        documents = await self._load_documents(project_id)

        change_summary = self._build_summary(
            previous is None, new_items, modified_items, deleted_items
        )

        await self.db.execute(
            text(
                """
                UPDATE repository_versions
                SET is_current = FALSE
                WHERE project_id = :project_id AND is_current
                """
            ),
            {"project_id": project_id},
        )

        result = await self.db.execute(
            text(
                f"""
                INSERT INTO repository_versions (
                    project_id, version_number, is_current, change_summary,
                    total_requirements, approved_requirements,
                    pending_requirements, rejected_requirements,
                    new_count, modified_count, deleted_count,
                    changes, snapshot, documents, created_by
                )
                VALUES (
                    :project_id, :version_number, TRUE, :change_summary,
                    :total, :approved, :pending, :rejected,
                    :new_count, :modified_count, :deleted_count,
                    CAST(:changes AS jsonb),
                    CAST(:snapshot AS jsonb),
                    CAST(:documents AS jsonb),
                    :created_by
                )
                RETURNING {_LIST_COLUMNS}
                """
            ),
            {
                "project_id": project_id,
                "version_number": version_number,
                "change_summary": change_summary,
                "total": len(current_items),
                "approved": statuses.count("approved"),
                "pending": statuses.count("pending"),
                "rejected": statuses.count("rejected"),
                "new_count": len(new_items),
                "modified_count": len(modified_items),
                "deleted_count": len(deleted_items),
                "changes": json.dumps(
                    {
                        "new": new_items,
                        "modified": modified_items,
                        "deleted": deleted_items,
                    },
                    default=str,
                ),
                "snapshot": json.dumps(current_items, default=str),
                "documents": json.dumps(documents, default=str),
                "created_by": created_by,
            },
        )

        row = dict(result.mappings().one())

        print(
            f"[REPOSITORY VERSION] Project {project_id}: created "
            f"V{version_number} ({change_summary})."
        )

        return row

    # ---------------------------------------------------------------
    # Read: list + summary cards
    # ---------------------------------------------------------------

    async def list_versions(
        self,
        project_id: UUID,
        search: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        where = "WHERE rv.project_id = :project_id"
        params: dict = {"project_id": project_id}

        term = (search or "").strip()

        if term:
            params["like"] = f"%{term}%"
            where += """
                AND (
                    ('v' || rv.version_number::text) ILIKE :like
                    OR rv.version_number::text ILIKE :like
                    OR to_char(rv.created_at, 'DD Mon YYYY') ILIKE :like
                    OR to_char(rv.created_at, 'YYYY-MM-DD') ILIKE :like
                    OR (CASE WHEN rv.is_current
                             THEN 'current' ELSE 'previous' END) ILIKE :like
                    OR COALESCE(rv.change_summary, '') ILIKE :like
                )
            """

        total = (
            await self.db.execute(
                text(f"SELECT COUNT(*) FROM repository_versions rv {where}"),
                params,
            )
        ).scalar_one()

        result = await self.db.execute(
            text(
                f"""
                SELECT {_LIST_COLUMNS_QUALIFIED}
                FROM repository_versions rv
                {where}
                ORDER BY rv.version_number DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {**params, "limit": limit, "offset": offset},
        )

        return [dict(row) for row in result.mappings().all()], int(total)

    async def get_summary(self, project_id: UUID) -> dict:
        """Numbers for the six summary cards."""

        total = (
            await self.db.execute(
                text(
                    "SELECT COUNT(*) FROM repository_versions "
                    "WHERE project_id = :project_id"
                ),
                {"project_id": project_id},
            )
        ).scalar_one()

        result = await self.db.execute(
            text(
                """
                SELECT version_number, is_current,
                       approved_requirements, pending_requirements,
                       modified_count
                FROM repository_versions
                WHERE project_id = :project_id
                ORDER BY version_number DESC
                LIMIT 2
                """
            ),
            {"project_id": project_id},
        )
        rows = [dict(row) for row in result.mappings().all()]

        current = rows[0] if rows else None
        previous = rows[1] if len(rows) > 1 else None

        return {
            "total_versions": int(total),
            "current_version": current["version_number"] if current else None,
            "previous_version": previous["version_number"] if previous else None,
            "approved_requirements": (
                current["approved_requirements"] if current else 0
            ),
            "modified_requirements": (
                current["modified_count"] if current else 0
            ),
            "pending_requirements": (
                current["pending_requirements"] if current else 0
            ),
        }

    # ---------------------------------------------------------------
    # Read: one version (drawer)
    # ---------------------------------------------------------------

    async def get_version(
        self,
        project_id: UUID,
        version_id: UUID,
    ) -> dict | None:
        result = await self.db.execute(
            text(
                """
                SELECT
                    rv.id, rv.project_id, rv.version_number, rv.is_current,
                    rv.change_summary, rv.total_requirements,
                    rv.approved_requirements, rv.pending_requirements,
                    rv.rejected_requirements, rv.new_count,
                    rv.modified_count, rv.deleted_count,
                    rv.changes, rv.documents, rv.snapshot, rv.created_at,
                    u.full_name AS created_by_name,
                    u.role::text AS created_by_role
                FROM repository_versions rv
                LEFT JOIN users u ON u.id = rv.created_by
                WHERE rv.id = :version_id
                  AND rv.project_id = :project_id
                """
            ),
            {"version_id": version_id, "project_id": project_id},
        )

        row = result.mappings().first()

        if row is None:
            return None

        data = dict(row)
        data["changes"] = _as_json(
            data.get("changes"),
            {"new": [], "modified": [], "deleted": []},
        )
        data["documents"] = _as_json(data.get("documents"), [])

        # The full requirement list is only needed for the first
        # (baseline) version, which has nothing to compare against.
        snapshot = _as_json(data.pop("snapshot", None), [])
        data["is_baseline"] = int(data["version_number"]) == 1
        data["requirements"] = (
            [
                {
                    "requirement_id": item.get("requirement_id"),
                    "requirement_code": item.get("requirement_code"),
                    "title": item.get("title"),
                    "status": item.get("status"),
                }
                for item in snapshot
            ]
            if data["is_baseline"]
            else []
        )

        return data
