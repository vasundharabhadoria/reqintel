"""
Data access for the signed-in user's own profile and for account deletion.

Every statement runs on the per-request AsyncSession, i.e. as the
`reqintel_app` role with the RLS user set by db.session.get_db, so the
database itself also limits each query to the caller's own rows.

Profile writes are deliberately column-specific: only full_name can ever be
changed here. role, is_active, email and id are never part of an UPDATE.
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_PROFILE_COLUMNS = (
    "id::text AS id, full_name, email::text AS email, role::text AS role, "
    "is_active, created_at, last_login_at"
)


class ProfileRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def set_rls_context(self, user_id: UUID) -> None:
        """set_config(..., true) lasts for ONE transaction: repeat after commit/rollback."""

        await self.db.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(user_id)},
        )

    async def get(self, user_id: UUID) -> dict | None:
        result = await self.db.execute(
            text(f"SELECT {_PROFILE_COLUMNS} FROM users WHERE id = :id"),
            {"id": user_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def update_full_name(self, user_id: UUID, full_name: str) -> dict | None:
        result = await self.db.execute(
            text(
                f"UPDATE users SET full_name = :name WHERE id = :id "
                f"RETURNING {_PROFILE_COLUMNS}"
            ),
            {"id": user_id, "name": full_name},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    # ---------------------------------------------------------------
    # Account deletion helpers
    # ---------------------------------------------------------------

    async def list_owned_projects(self, user_id: UUID) -> list[dict]:
        """Every project the user owns, in ANY status (active, archived, ...)."""

        result = await self.db.execute(
            text(
                "SELECT id, name FROM projects WHERE owner_id = :u "
                "ORDER BY created_at, id"
            ),
            {"u": user_id},
        )
        return [dict(r) for r in result.mappings().all()]

    async def count_blocking_references(self, user_id: UUID) -> dict[str, int]:
        """
        Rows that still reference users(id) through an ON DELETE RESTRICT
        foreign key (verified against the live database). Deleting the auth
        user while any exist would fail, so the service checks first.
        """

        result = await self.db.execute(
            text(
                """
                SELECT
                  (SELECT COUNT(*) FROM projects
                     WHERE owner_id = :u)                   AS projects,
                  (SELECT COUNT(*) FROM requirement_sources
                     WHERE uploaded_by = :u)                AS requirement_sources,
                  (SELECT COUNT(*) FROM requirements
                     WHERE created_by = :u)                 AS requirements,
                  (SELECT COUNT(*) FROM requirement_versions
                     WHERE created_by = :u)                 AS requirement_versions,
                  (SELECT COUNT(*) FROM requirement_traceability
                     WHERE mapped_by = :u)                  AS requirement_traceability,
                  (SELECT COUNT(*) FROM requirement_test_cases
                     WHERE mapped_by = :u)                  AS requirement_test_cases,
                  (SELECT COUNT(*) FROM reports
                     WHERE generated_by = :u)               AS reports
                """
            ),
            {"u": user_id},
        )
        return {k: int(v) for k, v in dict(result.mappings().one()).items()}
