class AuthError(Exception):
    """Base exception for authentication errors."""


class RegistrationError(AuthError):
    """Raised when user registration fails."""


class AuthenticationError(AuthError):
    """Raised when login or token authentication fails."""


class UserNotFoundError(AuthError):
    """Raised when an authenticated user cannot be found."""