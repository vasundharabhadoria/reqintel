from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.repository_version import (
    RepositoryVersionDetail,
    RepositoryVersionItem,
    RepositoryVersionListResponse,
    RepositoryVersionSummary,
)
from services.project_repository import ProjectRepository
from services.repository_version_repository import RepositoryVersionRepository


class VersionService:
    """
    Read side of repository versions (Versions tab).

    Versions are CREATED by RequirementService after an analysis, never
    by an API call from the browser.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.projects = ProjectRepository(db)
        self.repo = RepositoryVersionRepository(db)

    async def _require_project(self, owner_id: UUID, project_id: UUID) -> None:
        project = await self.projects.get_by_id(project_id, owner_id)

        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

    async def list_versions(
        self,
        owner_id: UUID,
        project_id: UUID,
        search: str | None,
        page: int,
        page_size: int,
    ) -> RepositoryVersionListResponse:
        await self._require_project(owner_id, project_id)

        rows, total = await self.repo.list_versions(
            project_id,
            search,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        summary = await self.repo.get_summary(project_id)

        return RepositoryVersionListResponse(
            summary=RepositoryVersionSummary(**summary),
            total=total,
            page=page,
            page_size=page_size,
            items=[RepositoryVersionItem(**row) for row in rows],
        )

    async def get_version(
        self,
        owner_id: UUID,
        project_id: UUID,
        version_id: UUID,
    ) -> RepositoryVersionDetail:
        await self._require_project(owner_id, project_id)

        row = await self.repo.get_version(project_id, version_id)

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository version not found.",
            )

        return RepositoryVersionDetail(**row)
