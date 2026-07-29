from supabase import Client
from supabase_auth.errors import AuthApiError

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


class AuthService:
    """Business logic for Supabase authentication."""

    def __init__(self, supabase: Client) -> None:
        self.supabase = supabase

    def signup(self, payload: SignUpRequest) -> UserResponse:
        """Register a new user using Supabase Auth."""

        try:
            response = self.supabase.auth.sign_up(
                {
                    "email": str(payload.email),
                    "password": payload.password,
                    "options": {
                        "data": {
                            "full_name": payload.full_name,
                        }
                    },
                }
            )

        except AuthApiError as exc:
            raise RegistrationError(str(exc)) from exc

        if response.user is None:
            raise RegistrationError(
                "User registration failed."
            )

        if response.user.email is None:
            raise RegistrationError(
                "Supabase did not return an email for the new user."
            )

        return UserResponse(
            id=str(response.user.id),
            email=response.user.email,
        )

    def login(self, payload: LoginRequest) -> TokenResponse:
        """Authenticate a user and return session tokens."""

        try:
            response = self.supabase.auth.sign_in_with_password(
                {
                    "email": str(payload.email),
                    "password": payload.password,
                }
            )

        except AuthApiError as exc:
            raise AuthenticationError(
                "Invalid email or password."
            ) from exc

        if response.session is None:
            raise AuthenticationError(
                "Authentication succeeded but no session was returned."
            )

        return TokenResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
        )

    def logout(self, access_token: str) -> None:
        """Sign out the session represented by the access token."""

        try:
            self.supabase.auth.admin.sign_out(
                access_token,
                scope="local",
            )

        except AuthApiError as exc:
            raise AuthenticationError(
                "Logout failed."
            ) from exc