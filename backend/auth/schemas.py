from pydantic import BaseModel, EmailStr, Field


class SignUpRequest(BaseModel):
    """Data required to register a new user."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)


class LoginRequest(BaseModel):
    """Data required to authenticate a user."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Authentication tokens returned after login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public information about an authenticated user."""

    id: str
    email: EmailStr
    role: str = "business_analyst"
