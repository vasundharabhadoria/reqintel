import asyncio
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from core.storage import REPORTS_BUCKET
from models.report import ReportResponse
from services.project_repository import ProjectRepository
from services.project_storage_cleanup import is_safe_object, remove_objects
from services.report_builder import FORMAT_INFO, build_report_data
from services.report_repository import ReportRepository

logger = logging.getLogger(__name__)

ACTION_GENERATED = "REPORT_GENERATED"
ACTION_DELETED = "REPORT_DELETED"


def build_file_name(
    project_name: str, generated_at: datetime, report_format: str
) -> str:
    """ASCII-only download name: <project>_report_<UTC timestamp>.<ext>."""

    ascii_name = (
        unicodedata.normalize("NFKD", project_name or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_name).strip("_")[:50] or "project"

    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    stamp = generated_at.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S")
    extension = FORMAT_INFO.get(report_format, {}).get("extension", report_format)

    return f"{slug}_report_{stamp}.{extension}"


class ReportService:
    """
    Business logic for report generation, listing, download and deletion.

    Safety rules:
      * every operation is scoped to the authenticated owner; a report or
        project that is not theirs is a 404 and its existence is never
        revealed;
      * the file is uploaded BEFORE the database row is inserted, and the
        row and its activity-log entry are committed together. If the
        database step fails, the uploaded file is removed again;
      * nothing is logged as generated unless the file is stored AND the row
        is committed;
      * raw exceptions are logged, never returned to the client.
    """

    def __init__(self, db: AsyncSession, storage_client: Any | None = None) -> None:
        self.db = db
        self.repo = ReportRepository(db)
        self.projects = ProjectRepository(db)
        self._storage_client = storage_client

    @property
    def storage(self) -> Any:
        if self._storage_client is None:
            from core.storage import get_storage_client

            self._storage_client = get_storage_client()

        return self._storage_client

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------

    async def _rollback(self) -> None:
        try:
            await self.db.rollback()
        except Exception:
            logger.exception("Rollback failed")

    def _upload(self, path: str, content: bytes, content_type: str) -> None:
        self.storage.storage.from_(REPORTS_BUCKET).upload(
            path,
            content,
            {"content-type": content_type},
        )

    def _download(self, path: str) -> bytes:
        return self.storage.storage.from_(REPORTS_BUCKET).download(path)

    async def _discard_object(self, path: str) -> None:
        """Best-effort removal of a file whose database row was never saved."""

        try:
            failed = await remove_objects(
                self.storage, [{"bucket": REPORTS_BUCKET, "path": path}]
            )
        except Exception:
            failed = [{"bucket": REPORTS_BUCKET, "path": path}]

        if failed:
            logger.error(
                "Orphaned report file could not be removed: %s/%s",
                REPORTS_BUCKET,
                path,
            )

    @staticmethod
    def _to_response(row: dict) -> ReportResponse:
        return ReportResponse.model_validate(
            {
                **row,
                "file_name": build_file_name(
                    row["project_name"], row["generated_at"], row["report_format"]
                ),
            }
        )

    async def _get_row(self, owner_id: UUID, report_id: UUID) -> dict:
        row = await self.repo.get_for_owner(report_id, owner_id)

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found.",
            )

        return row

    # ---------------------------------------------------------------
    # Generate
    # ---------------------------------------------------------------

    async def generate_report(
        self,
        owner_id: UUID,
        owner_email: str | None,
        project_id: UUID,
        report_format: str,
    ) -> ReportResponse:
        info = FORMAT_INFO.get(report_format)

        if info is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported report format.",
            )

        project = await self.projects.get_by_id(project_id, owner_id)

        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        try:
            requirement_rows = await self.repo.fetch_requirements(
                project_id, owner_id
            )
            suggestion_rows = await self.repo.fetch_suggestions(
                [
                    row["ai_analysis_id"]
                    for row in requirement_rows
                    if row.get("ai_analysis_id") is not None
                ]
            )
        except Exception as exc:
            logger.exception("Could not read data for report of project %s", project_id)
            await self._rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to read the project data for the report.",
            ) from exc

        generated_at = datetime.now(timezone.utc)

        try:
            data = build_report_data(
                project, requirement_rows, suggestion_rows, generated_at, owner_email
            )
            content = await asyncio.to_thread(info["builder"], data)

            if not content:
                raise ValueError("The report builder returned no content.")
        except Exception as exc:
            logger.exception(
                "%s report generation failed for project %s",
                report_format.upper(),
                project_id,
            )
            await self._rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate the {report_format.upper()} report.",
            ) from exc

        report_id = uuid4()
        file_path = f"{project_id}/{report_id}.{info['extension']}"

        try:
            await asyncio.to_thread(
                self._upload, file_path, content, info["content_type"]
            )
        except Exception as exc:
            logger.exception("Report upload failed for project %s", project_id)
            await self._rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store the generated report. Please try again.",
            ) from exc

        try:
            row = await self.repo.insert_report(
                report_id=report_id,
                project_id=project_id,
                owner_id=owner_id,
                report_format=report_format,
                file_path=file_path,
                generated_at=generated_at,
                includes_validation=False,
                includes_ai_suggestions=True,
                includes_quality_scores=True,
                includes_change_impact=False,
            )

            if row is None:
                raise LookupError("Report row was not inserted (project not owned).")

            await self.repo.log_activity(
                owner_id,
                ACTION_GENERATED,
                report_id,
                {
                    "project_id": str(project_id),
                    "project_name": project["name"],
                    "report_format": report_format,
                    "requirements": len(requirement_rows),
                },
            )
            await self.db.commit()
            response = self._to_response(row)
        except Exception as exc:
            logger.exception(
                "Report metadata could not be saved for project %s", project_id
            )
            await self._rollback()
            await self._discard_object(file_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save the report. Please try again.",
            ) from exc

        return response

    # ---------------------------------------------------------------
    # Read
    # ---------------------------------------------------------------

    async def list_reports(
        self,
        owner_id: UUID,
        project_id: UUID | None,
        report_format: str | None,
        limit: int,
    ) -> list[ReportResponse]:
        rows = await self.repo.list_for_owner(
            owner_id, project_id, report_format, limit
        )

        items: list[ReportResponse] = []

        for row in rows:
            try:
                items.append(self._to_response(row))
            except (ValidationError, KeyError, TypeError):
                # One bad row must not break the whole list.
                logger.error("Skipping report %s with invalid metadata", row.get("id"))

        return items

    async def get_report(self, owner_id: UUID, report_id: UUID) -> ReportResponse:
        row = await self._get_row(owner_id, report_id)

        try:
            return self._to_response(row)
        except (ValidationError, KeyError, TypeError) as exc:
            logger.error("Report %s has invalid metadata", report_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The report metadata is invalid.",
            ) from exc

    # ---------------------------------------------------------------
    # Download
    # ---------------------------------------------------------------

    async def download_report(self, owner_id: UUID, report_id: UUID) -> Response:
        row = await self._get_row(owner_id, report_id)

        path = row.get("file_path")
        info = FORMAT_INFO.get(row.get("report_format"))

        if (
            info is None
            or not path
            or not is_safe_object(row["project_id"], REPORTS_BUCKET, path)
        ):
            logger.error("Report %s has no usable stored file path", report_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The report file is not available.",
            )

        try:
            content = await asyncio.to_thread(self._download, path)
        except Exception as exc:
            logger.exception("Report download failed for %s", report_id)

            if "not found" in str(exc).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="The report file is no longer available.",
                ) from exc

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve the report file.",
            ) from exc

        if not content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The report file is empty or missing.",
            )

        file_name = build_file_name(
            row["project_name"], row["generated_at"], row["report_format"]
        )

        return Response(
            content=content,
            media_type=info["content_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )

    # ---------------------------------------------------------------
    # Delete
    # ---------------------------------------------------------------

    async def delete_report(self, owner_id: UUID, report_id: UUID) -> None:
        await self._get_row(owner_id, report_id)

        try:
            deleted = await self.repo.delete_for_owner(report_id, owner_id)

            if deleted is None:
                logger.warning(
                    "DELETE removed no row for report %s although it was found "
                    "(concurrent delete, or a missing reports DELETE policy)",
                    report_id,
                )
                await self._rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="The report could not be deleted.",
                )

            await self.repo.log_activity(
                owner_id,
                ACTION_DELETED,
                report_id,
                {
                    "project_id": str(deleted["project_id"]),
                    "project_name": deleted["project_name"],
                    "report_format": deleted["report_format"],
                },
            )
            await self.db.commit()
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Report deletion failed for %s", report_id)
            await self._rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete the report. Please try again.",
            ) from exc

        # The database is the source of truth: the stored file is removed
        # only after the row is gone. A failure here leaves an unreferenced
        # file, which is logged but does not fail the request.
        path = deleted.get("file_path")

        if path and is_safe_object(deleted["project_id"], REPORTS_BUCKET, path):
            await self._discard_object(path)