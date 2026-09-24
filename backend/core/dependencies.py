from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from auth.exceptions import AuthenticationError
from auth.schemas import UserResponse
from core.security import verify_access_token
from core.supabase import supabase

bearer_scheme = HTTPBearer(auto_error=False)


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
        supabase.postgrest.auth(access_token)

        response = (
            supabase
            .from_("users")
            .select("role")
            .eq("id", user_id)
            .single()
            .execute()
        )

    except Exception as exc:
        print("ROLE QUERY ERROR:", repr(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve user information.",
        ) from exc

    if response.data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User profile was not found.",
        )

    role = response.data.get("role")

    if not role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User role was not found.",
        )

    return UserResponse(
        id=str(user_id),
        email=str(email),
        role=role,
    )