from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.schemas import UserResponse
from core.dependencies import get_current_user
from db.session import get_db
from models.report import (
    ReportFormat,
    ReportGenerateRequest,
    ReportListResponse,
    ReportResponse,
)
from services.report_service import ReportService

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


@router.post(
    "",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_report(
    payload: ReportGenerateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """Generate a PDF, XLSX or HTML report for a project owned by the caller."""

    service = ReportService(db)
    return await service.generate_report(
        UUID(current_user.id),
        current_user.email,
        payload.project_id,
        payload.report_format,
    )


@router.get(
    "",
    response_model=ReportListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_reports(
    project_id: UUID | None = Query(default=None),
    report_format: ReportFormat | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportListResponse:
    """
    List the caller's generated reports, newest first.

    Supports `?project_id=<uuid>` and `?report_format=pdf|xlsx|html`.
    """

    service = ReportService(db)
    items = await service.list_reports(
        UUID(current_user.id), project_id, report_format, limit
    )
    return ReportListResponse(total=len(items), items=items)


@router.get(
    "/{report_id}",
    response_model=ReportResponse,
    status_code=status.HTTP_200_OK,
)
async def get_report(
    report_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """Metadata of one report owned by the caller."""

    service = ReportService(db)
    return await service.get_report(UUID(current_user.id), report_id)


@router.get("/{report_id}/download")
async def download_report(
    report_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download the stored file of a report owned by the caller."""

    service = ReportService(db)
    return await service.download_report(UUID(current_user.id), report_id)


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_report(
    report_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a report (database row and stored file) owned by the caller."""

    service = ReportService(db)
    await service.delete_report(UUID(current_user.id), report_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)