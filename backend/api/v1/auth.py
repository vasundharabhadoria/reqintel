from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from auth.exceptions import (
    AuthenticationError,
    RegistrationError,
)
from auth.schemas import (
    LoginRequest,
    SignUpRequest,
    TokenResponse,
    UserResponse,
)
from auth.service import AuthService
from core.dependencies import (
    bearer_scheme,
    get_current_user,
)
from core.supabase import supabase


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)

auth_service = AuthService(supabase)


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def signup(payload: SignUpRequest) -> UserResponse:
    """Register a new ReqIntel user."""

    try:
        return auth_service.signup(payload)

    except RegistrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def login(payload: LoginRequest) -> TokenResponse:
    """Authenticate a user."""

    try:
        return auth_service.login(payload)

    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def me(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Return the currently authenticated user."""

    return current_user


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, str]:
    """Sign out the current Supabase session."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        auth_service.logout(
            access_token=credentials.credentials,
        )

    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return {"message": "Logged out successfully."}