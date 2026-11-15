import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

FULL_NAME_MIN_LENGTH = 2
# public.users.full_name is VARCHAR(150). Longer names would make the
# auth.users -> public.users trigger fail, so the API must reject them first.
FULL_NAME_MAX_LENGTH = 150

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

OAuthProvider = Literal["google", "github"]


def validate_password_strength(value: str) -> str:
    """Shared password policy for sign-up and password reset."""

    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Password must contain at least {PASSWORD_MIN_LENGTH} characters."
        )

    if len(value) > PASSWORD_MAX_LENGTH:
        raise ValueError(
            f"Password must not exceed {PASSWORD_MAX_LENGTH} characters."
        )

    if not re.search(r"[a-z]", value):
        raise ValueError("Password must include a lowercase letter.")

    if not re.search(r"[A-Z]", value):
        raise ValueError("Password must include an uppercase letter.")

    if not re.search(r"\d", value):
        raise ValueError("Password must include a number.")

    return value


def _normalise_email(value: str) -> str:
    return str(value).strip().lower()


class SignUpRequest(BaseModel):
    """Data required to register a new user."""

    email: EmailStr
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)
    full_name: str = Field(max_length=FULL_NAME_MAX_LENGTH + 100)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _normalise_email(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        return validate_password_strength(value)

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, value: str) -> str:
        name = " ".join(value.split())

        if any(unicodedata.category(ch).startswith("C") for ch in name):
            raise ValueError("Full name contains invalid characters.")

        if len(name) < FULL_NAME_MIN_LENGTH:
            raise ValueError(
                f"Full name must contain at least {FULL_NAME_MIN_LENGTH} characters."
            )

        if len(name) > FULL_NAME_MAX_LENGTH:
            raise ValueError(
                f"Full name must not exceed {FULL_NAME_MAX_LENGTH} characters."
            )

        return name


class LoginRequest(BaseModel):
    """Data required to authenticate a user."""

    email: EmailStr
    # Deliberately NOT checked against the password policy: accounts created
    # before the policy existed must still be able to sign in.
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _normalise_email(value)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class EmailRequest(BaseModel):
    """Used by forgot-password and resend-confirmation."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _normalise_email(value)


class ResetPasswordRequest(BaseModel):
    access_token: str = Field(min_length=1, max_length=4096)
    new_password: str = Field(max_length=PASSWORD_MAX_LENGTH)

    @field_validator("new_password")
    @classmethod
    def _password(cls, value: str) -> str:
        return validate_password_strength(value)


class OAuthExchangeRequest(BaseModel):
    """PKCE code exchange. The verifier proves this browser started the flow."""

    code: str = Field(min_length=1, max_length=2048)
    # RFC 7636: verifier is 43-128 characters from the unreserved set.
    code_verifier: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9._~-]+$")


class TokenResponse(BaseModel):
    """Authentication tokens returned after login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


class OAuthUrlResponse(BaseModel):
    url: str


class UserResponse(BaseModel):
    """Public information about an authenticated user."""

    id: str
    email: EmailStr
    role: str = "business_analyst"
