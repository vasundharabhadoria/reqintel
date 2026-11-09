from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.project import ProjectCreate, ProjectResponse, ProjectUpdate
from services.project_repository import ProjectRepository


class ProjectService:
    """Business logic for project management. Owner scoping and the
    404-not-403 rule (never reveal another user's project exists) live
    here so every route gets the same behavior."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ProjectRepository(db)

    async def _log_activity(self, user_id: UUID, action: str, project_id: UUID) -> None:
        await self.db.execute(
            text(
                """
                INSERT INTO activity_logs (user_id, action, entity_type, entity_id)
                VALUES (:user_id, :action, 'project', :entity_id)
                """
            ),
            {"user_id": user_id, "action": action, "entity_id": project_id},
        )

    async def _commit(self) -> None:
        """
        Commit the request's transaction: the row change and its activity log
        together, so both persist or neither does. get_db() rolls back any
        transaction that is still open when the request ends, so a write that
        is never committed here is silently lost.
        """
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def create_project(
        self, owner_id: UUID, payload: ProjectCreate
    ) -> ProjectResponse:
        row = await self.repo.create(
            owner_id,
            payload.name,
            payload.client_name,
            payload.project_type,
            payload.description,
        )
        await self._log_activity(owner_id, "PROJECT_CREATED", row["id"])
        response = ProjectResponse.model_validate(row)
        await self._commit()
        return response

    async def list_projects(
        self, owner_id: UUID, status_filter: str | None, search: str | None
    ) -> list[ProjectResponse]:
        rows = await self.repo.list_for_owner(owner_id, status_filter, search)
        return [ProjectResponse.model_validate(row) for row in rows]

    async def get_project(self, owner_id: UUID, project_id: UUID) -> ProjectResponse:
        row = await self.repo.get_by_id(project_id, owner_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )
        return ProjectResponse.model_validate(row)

    async def update_project(
        self, owner_id: UUID, project_id: UUID, payload: ProjectUpdate
    ) -> ProjectResponse:
        row = await self.repo.update(
            project_id,
            owner_id,
            payload.name,
            payload.client_name,
            payload.project_type,
            payload.description,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )
        await self._log_activity(owner_id, "PROJECT_UPDATED", project_id)
        response = ProjectResponse.model_validate(row)
        await self._commit()
        return response

    async def archive_project(
        self, owner_id: UUID, project_id: UUID
    ) -> ProjectResponse:
        row = await self.repo.archive(project_id, owner_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )
        await self._log_activity(owner_id, "PROJECT_ARCHIVED", project_id)
        response = ProjectResponse.model_validate(row)
        await self._commit()
        return response

    async def update_project_status(
        self,
        owner_id: UUID,
        project_id: UUID,
        new_status: str,
    ) -> ProjectResponse:
        row = await self.repo.update_status(
            project_id,
            owner_id,
            new_status,
        )

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        await self._log_activity(
            owner_id,
            "PROJECT_STATUS_CHANGED",
            project_id,
        )

        response = ProjectResponse.model_validate(row)
        await self._commit()
        return response