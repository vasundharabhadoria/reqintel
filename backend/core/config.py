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

    @property
    def jwt_issuer(self) -> str:
        """Expected `iss` claim on Supabase-issued access tokens."""
        return f"{self.SUPABASE_URL.rstrip('/')}/auth/v1"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()