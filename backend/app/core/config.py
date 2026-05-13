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
    # https://callback.strataai.com.br (Caddy → 192.168.100.26:8000).
    # Em DEV: ngrok ou webhook.site tunelando pro uvicorn local.
    # Vazia em prod = request_fidc_estoque_report levanta QiTechAdapterError
    # antes de POSTar pra QiTech (evita callback orfao com host invalido).
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

    # ---------- Reconciler (Fase 1 do auto-heal QiTech, 2026-05-13) ----------
    # Loop periodico que detecta `gap` na janela de cobertura e enfileira
    # BackfillJob automaticamente. Substitui monitoria manual ("ja sincou
    # esse dia?", "ainda tem furo?"). Ver `services/reconciler.py` +
    # memoria project_qitech_reconciler.md.
    RECONCILER_ENABLED: bool = Field(default=True)
    # Janela em dias corridos. 30 cobre o caso operacional comum (operador
    # quer "ultimo mes sem furo") sem onerar a API com retro-fetch profundo.
    # Bumpar quando Fase 2 adicionar politica por endpoint.
    RECONCILER_LOOKBACK_DAYS: int = Field(default=30, ge=7, le=365)
    # Cadencia do tick em minutos. 30 e raro o suficiente pra nao competir
    # com sync regular (sync_dispatcher = 1 min) e frequente o suficiente
    # pra furos sumirem dentro de ~1h sem operador clicar.
    RECONCILER_TICK_MINUTES: int = Field(default=30, ge=5, le=180)

    # ---------- System health: token de servico (opcional) ----------
    # Bearer token para endpoints publicos de monitoramento (ex.:
    # /api/v1/system/endpoint-sync-status). Habilita observabilidade externa
    # (rotinas /schedule no Anthropic Cloud, uptime monitors) sem precisar de
    # JWT de usuario. None/vazia = endpoint retorna 503 (token nao configurado).
    # Gerar com: python -c "import secrets; print(secrets.token_hex(32))"
    SYSTEM_HEALTH_TOKEN: str = Field(default="", min_length=0)

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
