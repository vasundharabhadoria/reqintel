import truststore
truststore.inject_into_ssl()

import logging
import threading
import time
from collections.abc import Callable
from urllib.parse import urlencode

import httpx
from supabase import Client
from supabase_auth.errors import AuthApiError, AuthError as SupabaseAuthError

import core.dependencies as deps
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
from auth.schemas import (
    LoginRequest,
    OAuthProvider,
    SignUpRequest,
    TokenResponse,
)
from core.config import settings
from core.security import verify_access_token
from core.supabase import create_auth_client

logger = logging.getLogger(__name__)

_RATE_LIMIT_CODES = {
    "over_request_rate_limit",
    "over_email_send_rate_limit",
    "over_sms_send_rate_limit",
}

_PASSWORD_ERRORS = {
    "weak_password": "Password is too weak. Choose a stronger password.",
    "same_password": "New password must be different from your old password.",
}


_PROVIDER_LABELS = {"google": "Google", "github": "GitHub"}

_SETTINGS_TTL_OK = 60
_SETTINGS_TTL_UNKNOWN = 10
_settings_lock = threading.Lock()
_settings_cache: dict = {"at": 0.0, "ttl": 0, "value": None}


def fetch_enabled_providers() -> dict[str, bool] | None:
    """
    Which external providers are switched on in Supabase, read from the
    project's public /auth/v1/settings endpoint (cached briefly).

    Returns None when it cannot be determined (network problem). Callers
    must then fail OPEN and let Supabase itself decide, so a hiccup here can
    never block sign-in.
    """

    now = time.monotonic()

    with _settings_lock:
        if now - _settings_cache["at"] < _settings_cache["ttl"]:
            return _settings_cache["value"]

    value: dict[str, bool] | None

    try:
        response = httpx.get(
            f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/settings",
            headers={"apikey": settings.SUPABASE_ANON_KEY},
            timeout=5,
        )
        response.raise_for_status()
        value = {
            str(name): bool(enabled)
            for name, enabled in (response.json().get("external") or {}).items()
        }

    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Could not read Supabase auth settings: %s", type(exc).__name__)
        value = None

    with _settings_lock:
        _settings_cache.update(
            at=now,
            ttl=_SETTINGS_TTL_OK if value is not None else _SETTINGS_TTL_UNKNOWN,
            value=value,
        )

    return value


def reset_settings_cache() -> None:
    with _settings_lock:
        _settings_cache.update(at=0.0, ttl=0, value=None)


def _code(exc: Exception) -> str:
    return str(getattr(exc, "code", "") or "")


def _is_rate_limited(exc: Exception) -> bool:
    return _code(exc) in _RATE_LIMIT_CODES or getattr(exc, "status", None) == 429


class AuthService:
    """
    Business logic for Supabase authentication.

    Every operation obtains its own client from `client_factory`, so no
    authentication state is ever shared between requests.
    """

    def __init__(
        self,
        client_factory: Callable[[], Client] = create_auth_client,
    ) -> None:
        self.client_factory = client_factory

    # ------------------------------------------------------------------ #
    # Registration and email confirmation
    # ------------------------------------------------------------------ #

    def signup(self, payload: SignUpRequest) -> None:
        """
        Register a user. With email confirmation enabled Supabase does not
        reveal whether the address already exists, and neither do we: the
        caller always receives the same generic confirmation message.
        """

        try:
            self.client_factory().auth.sign_up(
                {
                    "email": payload.email,
                    "password": payload.password,
                    "options": {
                        "data": {"full_name": payload.full_name},
                        "email_redirect_to": f"{settings.frontend_url}/auth/callback",
                    },
                }
            )

        except AuthApiError as exc:
            code = _code(exc)

            if _is_rate_limited(exc):
                raise RateLimitedError(
                    "Too many emails were requested. Please try again later."
                ) from exc

            if code == "user_already_exists":
                # Do not reveal that the account exists.
                return

            if code in _PASSWORD_ERRORS:
                raise RegistrationError(_PASSWORD_ERRORS[code]) from exc

            if code in {"email_address_invalid", "validation_failed"}:
                raise RegistrationError("Enter a valid email address.") from exc

            if code in {"signup_disabled", "email_provider_disabled"}:
                raise RegistrationError("Sign-up is currently disabled.") from exc

            # Supabase's own message is not secret (it never contains the
            # password) and is the fastest way to find the real cause.
            message = str(exc)[:200]
            logger.warning(
                "Sign-up rejected by Supabase (status=%s, code=%s, message=%s)",
                getattr(exc, "status", None),
                code or "unknown",
                message,
            )

            lowered = message.lower()

            if "sending" in lowered and "email" in lowered:
                raise EmailDeliveryError(
                    "We couldn't send the confirmation email right now. "
                    "Please try again in a few minutes."
                ) from exc

            if "database error" in lowered:
                raise RegistrationError(
                    "Your account could not be created. Please try again, or "
                    "contact your administrator if this continues."
                ) from exc

            raise RegistrationError(
                "Registration failed. Please check your details and try again."
            ) from exc

    def resend_confirmation(self, email: str) -> None:
        """Re-send the signup confirmation email. Never reveals the account."""

        try:
            self.client_factory().auth.resend(
                {
                    "type": "signup",
                    "email": email,
                    "options": {
                        "email_redirect_to": f"{settings.frontend_url}/auth/callback",
                    },
                }
            )

        except AuthApiError as exc:
            if _is_rate_limited(exc):
                raise RateLimitedError(
                    "Too many emails were requested. Please try again later."
                ) from exc

            logger.warning("Resend confirmation failed (code=%s)", _code(exc) or "unknown")

    # ------------------------------------------------------------------ #
    # Login, refresh, logout
    # ------------------------------------------------------------------ #

    def login(self, payload: LoginRequest) -> TokenResponse:
        """Authenticate a user and return session tokens."""

        client = self.client_factory()

        try:
            response = client.auth.sign_in_with_password(
                {
                    "email": payload.email,
                    "password": payload.password,
                }
            )

        except AuthApiError as exc:
            if _is_rate_limited(exc):
                raise RateLimitedError(
                    "Too many attempts. Please wait and try again."
                ) from exc

            if _code(exc) == "email_not_confirmed":
                # Supabase only reports this after the password was correct,
                # so it does not allow probing for registered emails.
                raise EmailNotConfirmedError(
                    "Please confirm your email address before signing in."
                ) from exc

            raise AuthenticationError("Invalid email or password.") from exc

        if response.session is None or response.user is None:
            raise AuthenticationError(
                "Authentication succeeded but no session was returned."
            )

        self._require_active_profile(
            client,
            user_id=str(response.user.id),
            access_token=response.session.access_token,
        )

        return TokenResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
        )

    def verify_password(self, user_id: str, email: str, password: str) -> None:
        """
        Re-check the signed-in user's password (re-authentication for
        sensitive actions such as account deletion).

        `email` and `user_id` always come from the verified JWT, never from
        the client. The check signs in on a throw-away client; the session it
        creates is revoked straight away so no extra session is left behind.
        """

        client = self.client_factory()

        try:
            response = client.auth.sign_in_with_password(
                {"email": email, "password": password}
            )

        except AuthApiError as exc:
            if _is_rate_limited(exc):
                raise RateLimitedError(
                    "Too many attempts. Please wait and try again."
                ) from exc

            raise AuthenticationError("Incorrect password.") from exc

        if response.user is None or str(response.user.id) != str(user_id):
            raise AuthenticationError("Incorrect password.")

        if response.session is not None:
            try:
                client.auth.admin.sign_out(
                    response.session.access_token, scope="local"
                )
            except Exception:  # best effort: the session expires on its own
                logger.warning("Could not revoke the re-authentication session.")

    def refresh(self, refresh_token: str) -> TokenResponse:
        """
        Exchange a refresh token for a new access/refresh token pair.
        Supabase rotates refresh tokens, so the old one stops working.
        """

        client = self.client_factory()

        try:
            response = client.auth.refresh_session(refresh_token)

        except (AuthApiError, SupabaseAuthError) as exc:
            if _is_rate_limited(exc):
                raise RateLimitedError(
                    "Too many attempts. Please wait and try again."
                ) from exc

            raise AuthenticationError(
                "Your session has expired. Please sign in again."
            ) from exc

        if response.session is None or response.user is None:
            raise AuthenticationError(
                "Your session has expired. Please sign in again."
            )

        self._require_active_profile(
            client,
            user_id=str(response.user.id),
            access_token=response.session.access_token,
        )

        return TokenResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
        )

    def logout(self, access_token: str) -> None:
        """Sign out the session represented by the access token."""

        try:
            self.client_factory().auth.admin.sign_out(
                access_token,
                scope="local",
            )

        except AuthApiError as exc:
            raise AuthenticationError("Logout failed.") from exc

    # ------------------------------------------------------------------ #
    # Password recovery
    # ------------------------------------------------------------------ #

    def forgot_password(self, email: str) -> None:
        """Send a recovery email. Never reveals whether the account exists."""

        try:
            self.client_factory().auth.reset_password_for_email(
                email,
                {"redirect_to": f"{settings.frontend_url}/reset-password"},
            )

        except AuthApiError as exc:
            if _is_rate_limited(exc):
                raise RateLimitedError(
                    "Too many emails were requested. Please try again later."
                ) from exc

            logger.warning("Password recovery failed (code=%s)", _code(exc) or "unknown")

    def reset_password(self, access_token: str, new_password: str) -> None:
        """
        Set a new password using the short-lived token from the recovery
        email. The token is verified here with the same checks used for every
        API request, then used as the caller's own credential against
        Supabase, so the backend never needs the service-role key.
        """

        try:
            verify_access_token(access_token)

        except AuthenticationError as exc:
            raise PasswordResetError(
                "This reset link is invalid or has expired. Request a new one."
            ) from exc

        try:
            response = httpx.put(
                f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": settings.SUPABASE_ANON_KEY,
                    "Authorization": f"Bearer {access_token}",
                },
                json={"password": new_password},
                timeout=10,
            )

        except httpx.HTTPError as exc:
            logger.warning("Password update could not reach Supabase: %s", type(exc).__name__)
            raise PasswordResetError(
                "We could not update your password. Please try again."
            ) from exc

        if response.status_code == 200:
            return

        if response.status_code in (401, 403):
            raise PasswordResetError(
                "This reset link is invalid or has expired. Request a new one."
            )

        try:
            code = str(response.json().get("error_code") or "")
        except ValueError:
            code = ""

        if code in _PASSWORD_ERRORS:
            raise PasswordResetError(_PASSWORD_ERRORS[code])

        if response.status_code == 429:
            raise RateLimitedError("Too many attempts. Please wait and try again.")

        logger.warning(
            "Password update rejected (status=%s, code=%s)",
            response.status_code,
            code or "unknown",
        )
        raise PasswordResetError("We could not update your password. Please try again.")

    # ------------------------------------------------------------------ #
    # OAuth (PKCE)
    # ------------------------------------------------------------------ #

    def oauth_authorize_url(self, provider: OAuthProvider, code_challenge: str) -> str:
        """
        Build the Supabase authorize URL. The redirect target comes from
        server configuration, never from the request, so it cannot be used
        as an open redirect. No client secret is involved: those live in
        Supabase.
        """

        enabled = fetch_enabled_providers()

        if enabled is not None and not enabled.get(provider, False):
            label = _PROVIDER_LABELS.get(provider, provider)
            raise ProviderUnavailableError(
                f"Sign-in with {label} is not enabled for this application yet. "
                "Use email and password, or ask an administrator to enable it."
            )

        query = urlencode(
            {
                "provider": provider,
                "redirect_to": f"{settings.frontend_url}/auth/callback",
                "code_challenge": code_challenge,
                "code_challenge_method": "s256",
            }
        )

        return f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/authorize?{query}"

    def oauth_exchange(self, code: str, code_verifier: str) -> TokenResponse:
        """Exchange the OAuth code (+ PKCE verifier) for a Supabase session."""

        client = self.client_factory()

        try:
            response = client.auth.exchange_code_for_session(
                {"auth_code": code, "code_verifier": code_verifier}
            )

        except (AuthApiError, SupabaseAuthError) as exc:
            if _is_rate_limited(exc):
                raise RateLimitedError(
                    "Too many attempts. Please wait and try again."
                ) from exc

            raise OAuthError(
                "Sign-in could not be completed. The link may have expired. "
                "Please try again."
            ) from exc

        if response.session is None or response.user is None:
            raise OAuthError(
                "Sign-in could not be completed. Please try again."
            )

        try:
            self._require_active_profile(
                client,
                user_id=str(response.user.id),
                access_token=response.session.access_token,
            )

        except AccountDisabledError:
            raise

        except AuthenticationError as exc:
            raise OAuthError(
                "Your account profile could not be created from this provider. "
                "Make sure the provider account has a verified email address."
            ) from exc

        return TokenResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
        )

    # ------------------------------------------------------------------ #

    def _require_active_profile(
        self,
        client: Client,
        user_id: str,
        access_token: str,
    ) -> None:
        """
        Reject sessions for users with no profile row or a deactivated
        account, and revoke the session that was just created for them.
        """

        try:
            profile = deps.fetch_user_profile(user_id, access_token)

        except Exception as exc:
            logger.exception("Profile lookup failed for user %s", user_id)
            self._revoke(client, access_token)
            raise AuthenticationError(
                "Unable to sign you in right now. Please try again."
            ) from exc

        if profile is None:
            logger.error("Authenticated user %s has no public.users profile", user_id)
            self._revoke(client, access_token)
            raise AuthenticationError("Invalid email or password.")

        if not profile.get("is_active", True):
            self._revoke(client, access_token)
            raise AccountDisabledError(
                "This account has been deactivated. Contact your administrator."
            )

    @staticmethod
    def _revoke(client: Client, access_token: str) -> None:
        try:
            client.auth.admin.sign_out(access_token, scope="local")
        except Exception:  # best effort: the caller is already being rejected
            logger.warning("Could not revoke rejected session")
