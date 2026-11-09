import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.storage import REPORTS_BUCKET, REQUIREMENT_SOURCES_BUCKET
from models.project_deletion import (
    ProjectPermanentDeleteResponse,
    StorageCleanupRetryItem,
    StorageCleanupRetryResponse,
    StorageCleanupSummary,
)
from services.project_deletion_repository import (
    ACTION_CLEANUP_COMPLETED,
    ACTION_CLEANUP_FAILED,
    ACTION_DELETED,
    ProjectDeletionRepository,
)
from services.project_storage_cleanup import (
    is_safe_object,
    list_project_objects,
    remove_objects,
)

logger = logging.getLogger(__name__)

_BUCKETS_BY_KEY = {
    "requirement_sources": REQUIREMENT_SOURCES_BUCKET,
    "reports": REPORTS_BUCKET,
}


class _DeletionIntegrityError(Exception):
    """A DELETE removed fewer rows than expected; the transaction is rolled back."""


class ProjectDeletionService:
    """
    Permanent project deletion.

    1. Lock + owner-check the project, verify the typed confirmation name.
    2. Collect storage paths BEFORE touching the database.
    3. Delete every dependent row in FK order, then the project, and write
       the PROJECT_PERMANENTLY_DELETED event, in ONE transaction.
    4. COMMIT. Any failure before this point rolls everything back and
       storage is never touched.
    5. Only after the commit, remove the storage files and append a
       COMPLETED / FAILED event. A failure here never turns the (already
       committed) deletion into an error response.

    Activity logs are never modified or deleted: cleanup progress is
    recorded with new append-only events.
    """

    def __init__(self, db: AsyncSession, storage_client: Any | None = None) -> None:
        self.db = db
        self.repo = ProjectDeletionRepository(db)
        self._storage_client = storage_client

    @property
    def storage(self) -> Any:
        if self._storage_client is None:
            from core.storage import get_storage_client

            self._storage_client = get_storage_client()

        return self._storage_client

    # ---------------------------------------------------------------
    # Permanent delete
    # ---------------------------------------------------------------

    async def permanently_delete_project(
        self,
        owner_id: UUID,
        project_id: UUID,
        confirm_name: str,
    ) -> ProjectPermanentDeleteResponse:
        project = await self.repo.lock_owned_project(project_id, owner_id)

        # 404-not-403: never reveal that another user's project exists.
        if project is None:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        if confirm_name != project["name"]:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The confirmation name does not match the project name.",
            )

        correlation_id = uuid4()
        deleted_at = datetime.now(timezone.utc)

        try:
            counts = await self.repo.count_project_data(project_id)
            db_paths = await self.repo.collect_storage_paths(project_id)

            objects, skipped, listing_errors = await self._build_storage_objects(
                project_id, db_paths
            )

            await self._delete_in_order(owner_id, project_id, counts)

            await self.repo.log_event(
                owner_id,
                ACTION_DELETED,
                project_id,
                {
                    "project_id": str(project_id),
                    "project_name": project["name"],
                    "project_type": project["project_type"],
                    "project_status": project["status"],
                    "deleted_by": str(owner_id),
                    "deleted_at": deleted_at.isoformat(),
                    "correlation_id": str(correlation_id),
                    "deleted_counts": counts,
                    "storage_objects": objects,
                    "skipped_objects": skipped,
                    "storage_listing_errors": listing_errors,
                },
            )

            await self.db.commit()

        except _DeletionIntegrityError as exc:
            await self.db.rollback()
            logger.error("Permanent delete rolled back for %s: %s", project_id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "The project could not be fully deleted, so nothing was "
                    "changed. Check that the database DELETE policies "
                    "(sql/15_permanent_delete.sql) are applied."
                ),
            ) from exc

        except Exception as exc:
            await self.db.rollback()
            logger.exception("Permanent delete failed for %s", project_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The project could not be deleted. No data was changed. Please try again.",
            ) from exc

        # ---- database committed: from here on, never raise ----

        cleanup = await self._cleanup_after_commit(
            owner_id, project_id, correlation_id, objects
        )

        if cleanup.status == "failed":
            message = (
                "Project permanently deleted. "
                f"{cleanup.failed_files} stored file(s) could not be removed yet; "
                "cleanup can be retried."
            )
        else:
            message = "Project permanently deleted."

        return ProjectPermanentDeleteResponse(
            project_id=project_id,
            project_name=project["name"],
            deleted_at=deleted_at,
            correlation_id=correlation_id,
            deleted_counts=counts,
            storage_cleanup=cleanup,
            message=message,
        )

    async def _delete_in_order(
        self, owner_id: UUID, project_id: UUID, counts: dict[str, int]
    ) -> None:
        steps = (
            ("reports", self.repo.delete_reports, counts["reports"]),
            ("requirements", self.repo.delete_requirements, counts["requirements"]),
            (
                "requirement_sources",
                self.repo.delete_requirement_sources,
                counts["requirement_sources"],
            ),
            ("apis", self.repo.delete_apis, counts["apis"]),
            ("test_cases", self.repo.delete_test_cases, counts["test_cases"]),
            ("modules", self.repo.delete_modules, counts["modules"]),
        )

        for name, delete, expected in steps:
            removed = await delete(project_id)

            # Under RLS a missing DELETE policy removes 0 rows silently.
            if removed != expected:
                raise _DeletionIntegrityError(
                    f"{name}: expected to delete {expected} row(s), deleted {removed}"
                )

        # repository_versions / waivers / the rest cascade from these deletes.
        if await self.repo.delete_project(project_id, owner_id) != 1:
            raise _DeletionIntegrityError("projects: the project row was not deleted")

    # ---------------------------------------------------------------
    # Storage object discovery (read-only, before deletion)
    # ---------------------------------------------------------------

    async def _build_storage_objects(
        self, project_id: UUID, db_paths: dict[str, list[str]]
    ) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
        """
        DB-recorded paths plus anything physically under "<project_id>/"
        in each bucket (files whose DB row never committed). Paths outside
        the project's own folder are skipped, never deleted.
        """

        objects: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        listing_errors: list[str] = []

        for key, bucket in _BUCKETS_BY_KEY.items():
            paths = set(db_paths.get(key, []))

            try:
                paths.update(
                    await list_project_objects(self.storage, bucket, project_id)
                )
            except Exception as exc:
                logger.warning("Could not list %s/%s: %s", bucket, project_id, exc)
                listing_errors.append(bucket)

            for path in sorted(paths):
                entry = {"bucket": bucket, "path": path}

                if is_safe_object(project_id, bucket, path):
                    objects.append(entry)
                else:
                    skipped.append(entry)

        return objects, skipped, listing_errors

    # ---------------------------------------------------------------
    # Cleanup after commit
    # ---------------------------------------------------------------

    async def _cleanup_after_commit(
        self,
        owner_id: UUID,
        project_id: UUID,
        correlation_id: UUID,
        objects: list[dict[str, str]],
    ) -> StorageCleanupSummary:
        if not objects:
            return StorageCleanupSummary(
                status="not_required",
                total_files=0,
                failed_files=0,
                correlation_id=correlation_id,
            )

        failed = await self._remove_safely(objects)

        await self._record_cleanup_result(
            owner_id, project_id, correlation_id, objects, failed
        )

        return StorageCleanupSummary(
            status="failed" if failed else "completed",
            total_files=len(objects),
            failed_files=len(failed),
            correlation_id=correlation_id,
        )

    async def _remove_safely(
        self, objects: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        try:
            return await remove_objects(self.storage, objects)
        except Exception as exc:
            logger.exception("Storage cleanup raised: %s", exc)
            return list(objects)

    async def _record_cleanup_result(
        self,
        owner_id: UUID,
        project_id: UUID,
        correlation_id: UUID,
        objects: list[dict[str, str]],
        failed: list[dict[str, str]],
    ) -> None:
        """Append a COMPLETED/FAILED event. Never raises."""

        now = datetime.now(timezone.utc).isoformat()

        try:
            await self.repo.set_rls_context(owner_id)

            if failed:
                await self.repo.log_event(
                    owner_id,
                    ACTION_CLEANUP_FAILED,
                    project_id,
                    {
                        "project_id": str(project_id),
                        "correlation_id": str(correlation_id),
                        "failed_at": now,
                        "total_files": len(objects),
                        "failed_count": len(failed),
                        "failed_objects": failed,
                    },
                )
            else:
                await self.repo.log_event(
                    owner_id,
                    ACTION_CLEANUP_COMPLETED,
                    project_id,
                    {
                        "project_id": str(project_id),
                        "correlation_id": str(correlation_id),
                        "completed_at": now,
                        "removed_count": len(objects),
                    },
                )

            await self.db.commit()

        except Exception:
            await self.db.rollback()
            logger.exception(
                "Could not record storage cleanup result for %s", correlation_id
            )

    # ---------------------------------------------------------------
    # Retry (works without the project row)
    # ---------------------------------------------------------------

    async def retry_storage_cleanup(
        self, owner_id: UUID, correlation_id: UUID | None = None
    ) -> StorageCleanupRetryResponse:
        await self.repo.set_rls_context(owner_id)
        pending = await self.repo.list_pending_cleanups(owner_id, correlation_id)
        await self.db.rollback()  # read-only so far; release the transaction

        items: list[StorageCleanupRetryItem] = []

        for row in pending:
            details = row["details"]
            project_id: UUID = row["project_id"]
            cid_raw = details.get("correlation_id")

            if not cid_raw:
                continue

            cid = UUID(cid_raw)

            # Resume from the last failure's paths when there is one.
            last_failed = row["last_failed"] or {}
            candidates = last_failed.get("failed_objects") or details.get(
                "storage_objects", []
            )

            # Re-validate: only this project's own files in known buckets.
            objects = [
                {"bucket": o["bucket"], "path": o["path"]}
                for o in candidates
                if is_safe_object(project_id, o.get("bucket", ""), o.get("path", ""))
            ]

            failed = await self._remove_safely(objects) if objects else []

            await self._record_cleanup_result(owner_id, project_id, cid, objects, failed)

            items.append(
                StorageCleanupRetryItem(
                    correlation_id=cid,
                    project_id=project_id,
                    status="failed" if failed else "completed",
                    total_files=len(objects),
                    failed_files=len(failed),
                )
            )

        still_failing = sum(1 for i in items if i.status == "failed")

        return StorageCleanupRetryResponse(
            pending_found=len(pending),
            completed=len(items) - still_failing,
            still_failing=still_failing,
            items=items,
        )
