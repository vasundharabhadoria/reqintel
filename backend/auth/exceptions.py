class AuthError(Exception):
    """Base exception for authentication errors."""


class RegistrationError(AuthError):
    """Raised when user registration fails."""


class AuthenticationError(AuthError):
    """Raised when login or token authentication fails."""


class EmailNotConfirmedError(AuthenticationError):
    """Raised when valid credentials belong to an unconfirmed email."""


class AccountDisabledError(AuthenticationError):
    """Raised when the account exists but has been deactivated."""


class RateLimitedError(AuthError):
    """Raised when Supabase reports it is rate limiting this request."""


class PasswordResetError(AuthError):
    """Raised when a password reset link or new password is rejected."""


class OAuthError(AuthError):
    """Raised when an OAuth sign-in cannot be completed."""


class ProviderUnavailableError(AuthError):
    """Raised when an OAuth provider is switched off in Supabase."""


class EmailDeliveryError(AuthError):
    """Raised when Supabase could not send an auth email (SMTP problem)."""


class UserNotFoundError(AuthError):
    """Raised when an authenticated user cannot be found."""
