from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.schemas import UserResponse
from core.dependencies import get_current_user
from db.session import get_db
from models.dashboard import DashboardSummary
from services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


@router.get(
    "/summary",
    response_model=DashboardSummary,
    status_code=status.HTTP_200_OK,
)
async def get_dashboard_summary(
    activity_limit: int = Query(default=10, ge=1, le=50),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardSummary:
    """Workspace statistics and recent activity for the authenticated user."""

    service = DashboardService(db)
    return await service.get_summary(UUID(current_user.id), activity_limit)