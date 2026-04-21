"""Application settings loaded from environment."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from `.env` or process environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---------- App ----------
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # ---------- Database ----------
    DATABASE_URL: str = Field(
        ...,
        description="SQLAlchemy async URL: postgresql+asyncpg://user:pass@host:port/db",
    )
    DATABASE_ECHO: bool = False

    # ---------- JWT ----------
    JWT_SECRET_KEY: str = Field(..., min_length=16)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480  # 8h

    # ---------- CORS ----------
    CORS_ORIGINS: str = "http://localhost:3000"

    # ---------- Bitfin (optional in Sprint 1; used from Sprint 2+) ----------
    BITFIN_HOST: str = ""
    BITFIN_DATABASE: str = ""
    BITFIN_USER: str = ""
    BITFIN_PASSWORD: str = ""
    BITFIN_DRIVER: str = "ODBC Driver 17 for SQL Server"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance (loaded once per process)."""
    return Settings()  # type: ignore[call-arg]
