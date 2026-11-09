import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from postgrest import SyncPostgrestClient

from auth.exceptions import AuthenticationError
from auth.schemas import UserResponse
from core.config import settings
from core.security import verify_access_token
from core.supabase import supabase

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

_REST_URL = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1"


def _fetch_user_role(user_id: str, access_token: str) -> str | None:
    """
    Read the caller's own role from public.users using the caller's token.

    A short-lived client is created per request on purpose. The module-level
    `supabase` client is shared by every request, so setting a user's token
    on it lets concurrent requests overwrite each other's Authorization
    header and read the wrong user's row.

    Returns None when the user has no profile row.
    """

    client = SyncPostgrestClient(
        _REST_URL,
        headers={
            "apikey": settings.SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=10,
    )

    try:
        response = (
            client.from_("users")
            .select("role")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    finally:
        client.session.close()

    rows = response.data or []

    if not rows:
        return None

    return rows[0].get("role")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> UserResponse:
    """
    Return the authenticated user from a verified Supabase JWT.
    """

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = credentials.credentials

    try:
        claims = verify_access_token(
            token=access_token,
        )

    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = claims.get("sub")
    email = claims.get("email")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token does not contain a user ID.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token does not contain an email.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # NOTE: kept for Module 2/3 (rule engine, master module), which read
    # master_rules / rule_categories through the shared `supabase` client and
    # may rely on this header. It is NOT used for the role lookup below.
    supabase.postgrest.auth(access_token)

    try:
        role = _fetch_user_role(str(user_id), access_token)

    except Exception as exc:
        logger.exception("Role lookup failed for user %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve user information.",
        ) from exc

    if role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User profile was not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserResponse(
        id=str(user_id),
        email=str(email),
        role=role,
    )