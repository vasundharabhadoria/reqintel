"""
Permanent account deletion.

Order matters (all verified against the live schema, see sql/17):

  1. Re-authenticate: password for accounts with an email identity, a recent
     sign-in (amr timestamp) for OAuth-only accounts.
  2. Delete every project the user owns through the EXISTING
     ProjectDeletionService (one transaction per project, FK order, files
     removed after commit). Nothing here re-implements project deletion.
  3. Retry any storage cleanup that is still pending. The retry is keyed on
     the user's id, which stops working once the account is gone, so the
     account is NOT deleted while files remain.
  4. Confirm nothing still references users(id) through a RESTRICT foreign key.
  5. Delete the Supabase Auth user with the Admin API. That cascades to
     public.users and to auth.sessions / identities, which ends every session.
     activity_logs rows are kept but anonymised (user_id becomes NULL).

Every step is safe to repeat: if the request fails part-way, the user can
simply retry and it continues from where it stopped.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from supabase_auth.errors import AuthApiError

from auth.exceptions import AuthenticationError, RateLimitedError
from auth.profile_repository import ProfileRepository
from auth.schemas import AccountDeletionResponse, DeleteAccountRequest, UserResponse
from core.rate_limit import account_delete_limiter
from services.project_deletion_service import ProjectDeletionService

logger = logging.getLogger(__name__)

# OAuth-only users must have signed in this recently to delete the account.
RECENT_LOGIN_SECONDS = 10 * 60

_PROVIDER_LABELS = {"google": "Google", "github": "GitHub", "email": "email"}


class AccountDeletionError(Exception):
    """A deletion step failed; carries the HTTP status and a stable code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Claims helpers (also used by the profile endpoint)
# ---------------------------------------------------------------------------


def auth_providers(claims: dict[str, Any]) -> tuple[str, list[str]]:
    """(primary provider, all linked providers) from the verified JWT."""

    meta = claims.get("app_metadata") or {}
    primary = meta.get("provider") if isinstance(meta.get("provider"), str) else "email"
    providers = [p for p in (meta.get("providers") or []) if isinstance(p, str)]

    if primary not in providers:
        providers.insert(0, primary)

    return primary, providers


def reauth_method(providers: list[str]) -> str:
    return "password" if "email" in providers else "recent_login"


def last_authentication_time(claims: dict[str, Any]) -> int | None:
    """Newest sign-in timestamp in the token's `amr` claim, if any."""

    stamps = [
        int(entry["timestamp"])
        for entry in (claims.get("amr") or [])
        if isinstance(entry, dict) and isinstance(entry.get("timestamp"), (int, float))
    ]
    return max(stamps) if stamps else None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AccountDeletionService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        auth_service: Any,
        admin_client_factory: Callable[[], Any] | None = None,
        storage_client: Any | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.db = db
        self.auth_service = auth_service
        self._admin_client_factory = admin_client_factory
        self._now = now
        self.repo = ProfileRepository(db)
        self.projects = ProjectDeletionService(db, storage_client=storage_client)

    # ----------------------------------------------------------------
    async def delete_account(
        self,
        user: UserResponse,
        claims: dict[str, Any],
        payload: DeleteAccountRequest,
    ) -> AccountDeletionResponse:
        # The target is ALWAYS the verified token's subject, never client input.
        user_id = UUID(user.id)

        await self._reauthenticate(user, claims, payload)

        projects_deleted, files_removed = await self._delete_owned_projects(user_id)
        await self._finish_pending_storage_cleanup(user_id)
        await self._ensure_nothing_blocks_deletion(user_id)
        await self._delete_auth_user(user_id)

        logger.info(
            "Account %s deleted (%d project(s), %d stored file(s) removed).",
            user_id,
            projects_deleted,
            files_removed,
        )

        return AccountDeletionResponse(
            message="Your account and all of its data have been permanently deleted.",
            projects_deleted=projects_deleted,
            storage_files_removed=files_removed,
        )

    # ---------------------------------------------------------------- 1
    async def _reauthenticate(
        self, user: UserResponse, claims: dict[str, Any], payload: DeleteAccountRequest
    ) -> None:
        account_delete_limiter.hit(f"delete:{user.id}")

        _, providers = auth_providers(claims)

        if reauth_method(providers) == "password":
            if not payload.password:
                raise AccountDeletionError(
                    403, "reauth_required", "Enter your current password to confirm."
                )

            try:
                await asyncio.to_thread(
                    self.auth_service.verify_password,
                    user.id,
                    user.email,
                    payload.password,
                )
            except RateLimitedError as exc:
                raise HTTPException(status_code=429, detail=str(exc)) from exc
            except AuthenticationError as exc:
                raise AccountDeletionError(
                    403, "reauth_failed", "The password you entered is incorrect."
                ) from exc
            return

        signed_in_at = last_authentication_time(claims)

        if signed_in_at is None or self._now() - signed_in_at > RECENT_LOGIN_SECONDS:
            label = _PROVIDER_LABELS.get(providers[0], providers[0])
            raise AccountDeletionError(
                403,
                "reauth_required",
                f"For your security, sign in again with {label} and then retry "
                f"within {RECENT_LOGIN_SECONDS // 60} minutes.",
            )

    # ---------------------------------------------------------------- 2
    async def _delete_owned_projects(self, user_id: UUID) -> tuple[int, int]:
        await self.repo.set_rls_context(user_id)
        owned = await self.repo.list_owned_projects(user_id)
        await self.db.rollback()  # read-only so far; release the transaction

        deleted = 0
        files_removed = 0

        for project in owned:
            # The RLS context only lasts for one transaction and every project
            # deletion commits, so it has to be set again each time.
            await self.repo.set_rls_context(user_id)

            try:
                result = await self.projects.permanently_delete_project(
                    user_id, project["id"], project["name"]
                )
            except HTTPException as exc:
                if exc.status_code == 404:
                    continue  # already removed (e.g. a double-submitted request)

                logger.error(
                    "Account deletion stopped: project %s could not be deleted (%s).",
                    project["id"],
                    exc.detail,
                )
                raise AccountDeletionError(
                    500,
                    "project_delete_failed",
                    "One of your projects could not be deleted, so your account was "
                    "kept. Projects deleted so far are gone. Please try again.",
                ) from exc

            deleted += 1
            files_removed += (
                result.storage_cleanup.total_files - result.storage_cleanup.failed_files
            )

        return deleted, files_removed

    # ---------------------------------------------------------------- 3
    async def _finish_pending_storage_cleanup(self, user_id: UUID) -> None:
        try:
            outcome = await self.projects.retry_storage_cleanup(user_id)
        except Exception as exc:
            logger.exception("Storage cleanup retry crashed for %s", user_id)
            raise AccountDeletionError(
                502,
                "storage_cleanup_incomplete",
                "Some stored files could not be removed yet, so your account was "
                "kept. Please try again in a few minutes.",
            ) from exc

        if outcome.still_failing:
            logger.error(
                "Account deletion paused for %s: %d storage cleanup(s) still failing.",
                user_id,
                outcome.still_failing,
            )
            raise AccountDeletionError(
                502,
                "storage_cleanup_incomplete",
                "Some stored files could not be removed yet, so your account was "
                "kept. Please try again in a few minutes.",
            )

    # ---------------------------------------------------------------- 4
    async def _ensure_nothing_blocks_deletion(self, user_id: UUID) -> None:
        await self.repo.set_rls_context(user_id)
        remaining = await self.repo.count_blocking_references(user_id)
        await self.db.rollback()

        leftovers = {k: v for k, v in remaining.items() if v}

        if leftovers:
            logger.error("Account %s still referenced by %s", user_id, leftovers)
            raise AccountDeletionError(
                409,
                "account_has_remaining_data",
                "Some of your data could not be removed, so your account was kept.",
            )

    # ---------------------------------------------------------------- 5
    async def _delete_auth_user(self, user_id: UUID) -> None:
        def _delete() -> None:
            factory = self._admin_client_factory

            if factory is None:
                from core.supabase import create_admin_client

                factory = create_admin_client

            factory().auth.admin.delete_user(str(user_id))

        try:
            await asyncio.to_thread(_delete)
        except AuthApiError as exc:
            if getattr(exc, "status", None) == 404 or getattr(exc, "code", "") == "user_not_found":
                return  # already deleted: a repeated/concurrent request

            logger.critical(
                "Data removed but the Auth user %s could not be deleted: %s",
                user_id,
                exc,
            )
            raise AccountDeletionError(
                502,
                "auth_delete_failed",
                "Your data was removed, but your sign-in account could not be "
                "deleted yet. Please try again.",
            ) from exc
        except Exception as exc:
            logger.critical(
                "Data removed but the Auth user %s could not be deleted: %s",
                user_id,
                exc,
            )
            raise AccountDeletionError(
                502,
                "auth_delete_failed",
                "Your data was removed, but your sign-in account could not be "
                "deleted yet. Please try again.",
            ) from exc
