import logging
from collections.abc import Iterator

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

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

_REST_URL = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1"


def _new_postgrest_client(access_token: str) -> SyncPostgrestClient:
    """
    Build a short-lived PostgREST client that acts as the caller.

    A new client is created per use on purpose. A client shared by every
    request must never carry a user's token, because concurrent requests
    would overwrite each other's Authorization header and read or write as
    the wrong user.
    """

    return SyncPostgrestClient(
        _REST_URL,
        headers={
            "apikey": settings.SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=10,
    )


def fetch_user_profile(user_id: str, access_token: str) -> dict | None:
    """
    Read the caller's own role and active flag from public.users using the
    caller's token (so RLS applies).

    Returns None when the user has no profile row.
    """

    client = _new_postgrest_client(access_token)

    try:
        response = (
            client.from_("users")
            .select("role, is_active")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    finally:
        client.session.close()

    rows = response.data or []

    if not rows:
        return None

    return {
        "role": rows[0].get("role"),
        "is_active": bool(rows[0].get("is_active", True)),
    }


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

    try:
        profile = fetch_user_profile(str(user_id), access_token)

    except Exception as exc:
        logger.exception("Role lookup failed for user %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve user information.",
        ) from exc

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User profile was not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not profile["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "account_disabled",
                "message": "This account has been deactivated.",
            },
        )

    return UserResponse(
        id=str(user_id),
        email=str(email),
        role=profile["role"],
    )


def get_user_db(
    current_user: UserResponse = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> Iterator[SyncPostgrestClient]:
    """
    Per-request PostgREST client acting as the authenticated caller.

    Depends on get_current_user, so the token has already been verified and
    the account is known to be active. The client is closed after the
    response and is never shared with another request.
    """

    client = _new_postgrest_client(credentials.credentials)

    try:
        yield client
    finally:
        client.session.close()