from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_COLUMNS = (
    "id, name, client_name, project_type, description, status, owner_id, "
    "created_at, updated_at"
)


class ProjectRepository:
    """
    Data access for the `projects` table.

    Every query filters by owner_id explicitly (defense in depth) in
    addition to the RLS policies already enforced by the DB session
    (see db/session.py's set_config bridge). A row belonging to another
    user simply will not be found — callers turn that into a 404, never
    revealing that the project exists.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        owner_id: UUID,
        name: str,
        client_name: str | None,
        project_type: str | None,
        description: str | None,
    ) -> dict:
        result = await self.db.execute(
            text(
                f"""
                INSERT INTO projects (name, client_name, project_type, description, owner_id)
                VALUES (:name, :client_name, :project_type, :description, :owner_id)
                RETURNING {_COLUMNS}
                """
            ),
            {
                "name": name,
                "client_name": client_name,
                "project_type": project_type,
                "description": description,
                "owner_id": owner_id,
            },
        )
        return dict(result.mappings().one())

    async def list_for_owner(
        self,
        owner_id: UUID,
        status_filter: str | None,
        search: str | None,
    ) -> list[dict]:
        query = f"""
            SELECT {_COLUMNS}
            FROM projects
            WHERE owner_id = :owner_id
        """
        params: dict = {"owner_id": owner_id}

        if status_filter:
            query += " AND status = :status"
            params["status"] = status_filter

        if search:
            query += (
                " AND (name ILIKE :search OR client_name ILIKE :search "
                "OR project_type ILIKE :search)"
            )
            params["search"] = f"%{search}%"

        query += " ORDER BY created_at DESC"

        result = await self.db.execute(text(query), params)
        return [dict(row) for row in result.mappings().all()]

    async def get_by_id(self, project_id: UUID, owner_id: UUID) -> dict | None:
        result = await self.db.execute(
            text(
                f"""
                SELECT {_COLUMNS}
                FROM projects
                WHERE id = :project_id AND owner_id = :owner_id
                """
            ),
            {"project_id": project_id, "owner_id": owner_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def update(
        self,
        project_id: UUID,
        owner_id: UUID,
        name: str,
        client_name: str | None,
        project_type: str | None,
        description: str | None,
    ) -> dict | None:
        result = await self.db.execute(
            text(
                f"""
                UPDATE projects
                SET name = :name,
                    client_name = :client_name,
                    project_type = :project_type,
                    description = :description,
                    updated_at = now()
                WHERE id = :project_id AND owner_id = :owner_id
                RETURNING {_COLUMNS}
                """
            ),
            {
                "project_id": project_id,
                "owner_id": owner_id,
                "name": name,
                "client_name": client_name,
                "project_type": project_type,
                "description": description,
            },
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def archive(self, project_id: UUID, owner_id: UUID) -> dict | None:
        result = await self.db.execute(
            text(
                f"""
                UPDATE projects
                SET status = 'archived', updated_at = now()
                WHERE id = :project_id AND owner_id = :owner_id
                RETURNING {_COLUMNS}
                """
            ),
            {"project_id": project_id, "owner_id": owner_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def update_status(
        self,
        project_id: UUID,
        owner_id: UUID,
        new_status: str,
    ) -> dict | None:
        result = await self.db.execute(
            text(
                f"""
                UPDATE projects
                SET status = :status,
                    updated_at = now()
                WHERE id = :project_id
                  AND owner_id = :owner_id
                RETURNING {_COLUMNS}
                """
            ),
            {
                "project_id": project_id,
                "owner_id": owner_id,
                "status": new_status,
            },
        )

        row = result.mappings().first()
        return dict(row) if row else None