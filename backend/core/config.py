from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application configuration."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SUPABASE_URL: str = Field(..., description="Supabase project URL")
    SUPABASE_ANON_KEY: str = Field(..., description="Supabase publishable key")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(
        ..., description="Supabase service role key"
    )
    SUPABASE_JWT_SECRET: str = Field(
        ..., description="Supabase JWT secret"
    )

    DATABASE_URL: str = Field(
        ...,
        description=(
            "Supabase Supavisor SESSION POOLER connection string, "
            "e.g. postgresql+asyncpg://postgres.<project-ref>:<password>"
            "@aws-0-<region>.pooler.supabase.com:5432/postgres"
        ),
    )

    FRONTEND_URL: str = Field(
        default="http://localhost:5173",
        description=(
            "Public URL of the React app. Used to build email-confirmation, "
            "password-recovery and OAuth redirect URLs. These URLs must also "
            "be allow-listed in Supabase (Authentication > URL Configuration)."
        ),
    )

    TRUST_PROXY_HEADERS: bool = Field(
        default=False,
        description=(
            "Read the client IP from X-Forwarded-For for rate limiting. "
            "Enable ONLY behind a reverse proxy you control."
        ),
    )

    @property
    def frontend_url(self) -> str:
        """FRONTEND_URL without a trailing slash."""
        return self.FRONTEND_URL.rstrip("/")

    @property
    def cors_origins(self) -> list[str]:
        """Origins allowed to call the API from a browser."""
        origins = {
            self.frontend_url,
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        }
        return sorted(origins)

    @property
    def jwt_issuer(self) -> str:
        """Expected `iss` claim on Supabase-issued access tokens."""
        return f"{self.SUPABASE_URL.rstrip('/')}/auth/v1"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()