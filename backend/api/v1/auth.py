from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from auth.exceptions import (
    AccountDisabledError,
    AuthenticationError,
    EmailDeliveryError,
    EmailNotConfirmedError,
    OAuthError,
    PasswordResetError,
    ProviderUnavailableError,
    RateLimitedError,
    RegistrationError,
)
from auth.account_service import (
    AccountDeletionError,
    AccountDeletionService,
    auth_providers,
    reauth_method,
)
from auth.profile_repository import ProfileRepository
from auth.schemas import (
    AccountDeletionResponse,
    DeleteAccountRequest,
    EmailRequest,
    LoginRequest,
    MessageResponse,
    OAuthExchangeRequest,
    OAuthProvider,
    OAuthUrlResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    RefreshRequest,
    ResetPasswordRequest,
    SignUpRequest,
    TokenResponse,
    UserResponse,
)
from auth.service import AuthService
from core.dependencies import (
    bearer_scheme,
    get_current_user,
    get_token_claims,
)
from core.rate_limit import (
    client_ip,
    email_action_account_limiter,
    email_action_ip_limiter,
    login_account_limiter,
    login_ip_limiter,
    oauth_limiter,
    per_ip,
    refresh_limiter,
    reset_limiter,
    signup_limiter,
)


from db.session import get_db


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)

auth_service = AuthService()

_CONFIRMATION_SENT = (
    "If this email address can be registered, a confirmation link has been "
    "sent. Check your inbox (and spam folder)."
)
_RECOVERY_SENT = (
    "If an account exists for this email address, a password reset link has "
    "been sent."
)
_CONFIRMATION_RESENT = (
    "If this account is awaiting confirmation, a new confirmation link has "
    "been sent."
)


def _too_many(exc: RateLimitedError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=str(exc),
        headers={"Retry-After": "60"},
    )


def _unauthorized(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=str(exc),
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(code: str, exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": code, "message": str(exc)},
    )


@router.post(
    "/signup",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(per_ip(signup_limiter))],
)
def signup(payload: SignUpRequest) -> MessageResponse:
    """Register a new ReqIntel user (email confirmation required)."""

    try:
        auth_service.signup(payload)

    except RateLimitedError as exc:
        raise _too_many(exc) from exc

    except EmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    except RegistrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return MessageResponse(message=_CONFIRMATION_SENT)


@router.post(
    "/resend-confirmation",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(per_ip(email_action_ip_limiter))],
)
def resend_confirmation(
    payload: EmailRequest,
    request: Request,
) -> MessageResponse:
    """Re-send the signup confirmation email."""

    email_action_account_limiter.hit(f"resend:{client_ip(request)}:{payload.email}")

    try:
        auth_service.resend_confirmation(payload.email)

    except RateLimitedError as exc:
        raise _too_many(exc) from exc

    return MessageResponse(message=_CONFIRMATION_RESENT)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(per_ip(login_ip_limiter))],
)
def login(payload: LoginRequest, request: Request) -> TokenResponse:
    """Authenticate a user."""

    login_account_limiter.hit(f"{client_ip(request)}:{payload.email}")

    try:
        return auth_service.login(payload)

    except RateLimitedError as exc:
        raise _too_many(exc) from exc

    except EmailNotConfirmedError as exc:
        raise _forbidden("email_not_confirmed", exc) from exc

    except AccountDisabledError as exc:
        raise _forbidden("account_disabled", exc) from exc

    except AuthenticationError as exc:
        raise _unauthorized(exc) from exc


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(per_ip(refresh_limiter))],
)
def refresh(payload: RefreshRequest) -> TokenResponse:
    """Exchange a refresh token for a new token pair (rotating)."""

    try:
        return auth_service.refresh(payload.refresh_token)

    except RateLimitedError as exc:
        raise _too_many(exc) from exc

    except AccountDisabledError as exc:
        raise _forbidden("account_disabled", exc) from exc

    except AuthenticationError as exc:
        raise _unauthorized(exc) from exc


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
        raise _unauthorized(exc) from exc

    return {"message": "Logged out successfully."}


def _profile_response(row: dict, claims: dict) -> ProfileResponse:
    primary, providers = auth_providers(claims)

    return ProfileResponse(
        **row,
        auth_provider=primary,
        providers=providers,
        reauth_method=reauth_method(providers),
    )


@router.get(
    "/profile",
    response_model=ProfileResponse,
    status_code=status.HTTP_200_OK,
)
async def get_profile(
    current_user: UserResponse = Depends(get_current_user),
    claims: dict = Depends(get_token_claims),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """The caller's own profile. The id always comes from the verified JWT."""

    row = await ProfileRepository(db).get(UUID(current_user.id))
    await db.rollback()  # read-only

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found.",
        )

    return _profile_response(row, claims)


@router.patch(
    "/profile",
    response_model=ProfileResponse,
    status_code=status.HTTP_200_OK,
)
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    claims: dict = Depends(get_token_claims),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Change the caller's full name. No other field can be modified."""

    row = await ProfileRepository(db).update_full_name(
        UUID(current_user.id), payload.full_name
    )

    if row is None:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found.",
        )

    await db.commit()
    return _profile_response(row, claims)


@router.delete(
    "/account",
    response_model=AccountDeletionResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_account(
    payload: DeleteAccountRequest,
    current_user: UserResponse = Depends(get_current_user),
    claims: dict = Depends(get_token_claims),
    db: AsyncSession = Depends(get_db),
) -> AccountDeletionResponse:
    """
    Permanently delete the CALLER's account and everything they own.

    There is no user id in the request: the target is the verified JWT's
    subject, so one user can never delete another. Requires typing DELETE
    plus re-authentication (see AccountDeletionService).
    """

    service = AccountDeletionService(db, auth_service=auth_service)

    try:
        return await service.delete_account(current_user, claims, payload)

    except AccountDeletionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(per_ip(email_action_ip_limiter))],
)
def forgot_password(
    payload: EmailRequest,
    request: Request,
) -> MessageResponse:
    """Send a password recovery email (same response for unknown emails)."""

    email_action_account_limiter.hit(f"recover:{client_ip(request)}:{payload.email}")

    try:
        auth_service.forgot_password(payload.email)

    except RateLimitedError as exc:
        raise _too_many(exc) from exc

    return MessageResponse(message=_RECOVERY_SENT)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(per_ip(reset_limiter))],
)
def reset_password(payload: ResetPasswordRequest) -> MessageResponse:
    """Set a new password using the token from the recovery email."""

    try:
        auth_service.reset_password(payload.access_token, payload.new_password)

    except RateLimitedError as exc:
        raise _too_many(exc) from exc

    except PasswordResetError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return MessageResponse(message="Your password has been updated. You can now sign in.")


@router.get(
    "/oauth/{provider}/url",
    response_model=OAuthUrlResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(per_ip(oauth_limiter))],
)
def oauth_url(
    provider: OAuthProvider,
    code_challenge: str,
) -> OAuthUrlResponse:
    """Return the provider authorize URL for a PKCE flow started by the browser."""

    # S256 challenge = base64url(SHA-256(verifier)) = exactly 43 characters.
    if len(code_challenge) != 43 or not all(
        ch.isalnum() or ch in "-_" for ch in code_challenge
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid code challenge.",
        )

    try:
        return OAuthUrlResponse(
            url=auth_service.oauth_authorize_url(provider, code_challenge)
        )

    except ProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post(
    "/oauth/exchange",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(per_ip(oauth_limiter))],
)
def oauth_exchange(payload: OAuthExchangeRequest) -> TokenResponse:
    """Exchange an OAuth authorization code (+ PKCE verifier) for tokens."""

    try:
        return auth_service.oauth_exchange(payload.code, payload.code_verifier)

    except RateLimitedError as exc:
        raise _too_many(exc) from exc

    except AccountDisabledError as exc:
        raise _forbidden("account_disabled", exc) from exc

    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
