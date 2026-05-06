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

    # ---------- Integracoes: criptografia de secrets ----------
    # KEK (Key Encryption Key) Fernet 32-byte URL-safe base64. Usada para
    # envelope encryption do campo `tenant_source_config.config`. Gerar com:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Em prod futuro: substituir por KMS (AWS/GCP) sem mudar call sites.
    APP_CONFIG_KEK: str = Field(..., min_length=32)

    # ---------- QiTech ----------
    # Secret usado pra HMAC-SHA256 do `jobId` no callback receiver da QiTech
    # (familia /v2/queue/scheduler/report/*). A QiTech NAO assina os
    # callbacks (validado em 2026-04-25 — sem header X-Signature ou JWT),
    # entao colocamos um token=hmac na query string do callbackUrl ao
    # criar o job. Receiver valida que token bate com hmac(jobId, secret),
    # bloqueando spoof de callbacks por terceiros que descubram a URL.
    # Gerar com: python -c "import secrets; print(secrets.token_hex(32))"
    QITECH_WEBHOOK_SECRET: str = Field(default="", min_length=0)

    # Base public URL onde a QiTech vai bater no callback. Em PROD:
    # https://callback.a7credit.com.br. Em DEV: ngrok ou webhook.site.
    QITECH_WEBHOOK_BASE_URL: str = Field(default="")

    # Credenciais de adapters (ex.: Bitfin) vivem em `tenant_source_config` — NAO aqui.
    # Cada tenant tem seu proprio banco (ver CLAUDE.md §13 regra 4).

    # Feature flag — agendamento por endpoint (refactor 2026-05-05).
    # False (default): dispatcher itera `tenant_source_config` e dispara sync da
    # integracao inteira (modo legado).
    # True: dispatcher itera `tenant_source_endpoint_config` e dispara endpoint a
    # endpoint, com schedule_kind ('interval'/'daily_at'/'on_demand') e
    # schedule_value proprios. Liga em staging primeiro, depois prod.
    INTEGRACOES_USE_ENDPOINT_SCHEDULING: bool = Field(default=False)

    # ---------- Credito: storage de anexos do dossie ----------
    # Diretorio raiz para blobs de anexos. Em dev defaults para um path local;
    # em prod sempre setar via env (caminho absoluto fora do repo).
    DOSSIER_STORAGE_ROOT: str = Field(default="./storage/dossier-attachments")
    # Tamanho maximo (bytes) por upload. Default 25 MB.
    DOSSIER_ATTACHMENT_MAX_BYTES: int = Field(default=26214400, ge=1)

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance (loaded once per process)."""
    return Settings()  # type: ignore[call-arg]
