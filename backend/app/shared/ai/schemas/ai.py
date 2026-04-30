"""Pydantic schemas for the AI HTTP layer."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AICapability, AIProvider

# ---------------------------------------------------------------------------
# Tenant-facing
# ---------------------------------------------------------------------------


class AIContext(BaseModel):
    """Page state attached to a chat request."""

    page: str
    period: str | None = None
    filters: str | None = None


class ChatRequest(BaseModel):
    """Body of POST /api/v1/ai/chat."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    context: AIContext
    conversation_id: UUID | None = None


class InsightItem(BaseModel):
    """A single bullet."""

    text: str


class InsightsResponse(BaseModel):
    """GET /api/v1/ai/insights."""

    insights: list[InsightItem]
    generated_at: datetime


class QuotaResponse(BaseModel):
    """GET /api/v1/ai/quota."""

    granted: int
    consumed: int
    carryover: int
    topup: int
    remaining: int
    exhausted: bool
    period_yyyymm: str


class ConversationListItem(BaseModel):
    """One row of GET /api/v1/ai/conversations."""

    id: UUID
    title: str | None
    page_context: str | None
    last_msg_at: datetime
    turn_count: int


class ConversationMessageRead(BaseModel):
    """One row of GET /api/v1/ai/conversations/{id}/messages.

    Only redacted text is exposed here. The encrypted original is fetched via
    a separate (system-maintainer-only) audit endpoint with full trail.
    """

    id: UUID
    turn_index: int
    role: str
    text: str
    occurred_at: datetime


# ---------------------------------------------------------------------------
# Admin (system maintainer)
# ---------------------------------------------------------------------------


class ProviderCredentialCreate(BaseModel):
    """POST /api/v1/admin/ai/providers."""

    model_config = ConfigDict(extra="forbid")

    provider: AIProvider
    alias: str = Field(min_length=1, max_length=64)
    api_key: str = Field(min_length=8)  # plaintext; encrypted on write
    org_id: str | None = None
    zdr_enabled: bool = False
    notes: str | None = None


class ProviderCredentialUpdate(BaseModel):
    """PUT /api/v1/admin/ai/providers/{id}."""

    model_config = ConfigDict(extra="forbid")

    api_key: str | None = None
    org_id: str | None = None
    zdr_enabled: bool | None = None
    active: bool | None = None
    notes: str | None = None


class ProviderCredentialRead(BaseModel):
    """GET /api/v1/admin/ai/providers — never returns the key itself."""

    id: UUID
    provider: AIProvider
    alias: str
    zdr_enabled: bool
    active: bool
    rotated_at: datetime | None
    notes: str | None
    created_at: datetime


class TenantAISubscriptionUpdate(BaseModel):
    """PUT /api/v1/admin/ai/subscriptions/{tenant_id}."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    plan_ref: str | None = None
    monthly_credit_quota: int = Field(ge=0)
    hard_cap_brl: Decimal | None = Field(default=None, ge=0)
    enabled_until: datetime | None = None
    grant_user_admin_to: list[UUID] = Field(
        default_factory=list,
        description="User ids in the tenant to grant AICapability.ADMIN to.",
    )
    grant_user_read_to: list[UUID] = Field(
        default_factory=list,
        description="User ids in the tenant to grant AICapability.READ to.",
    )


class TenantAISubscriptionRead(BaseModel):
    """GET /api/v1/admin/ai/subscriptions/{tenant_id}."""

    tenant_id: UUID
    enabled: bool
    plan_ref: str | None
    monthly_credit_quota: int
    hard_cap_brl: Decimal | None
    enabled_since: datetime | None
    enabled_until: datetime | None
    user_permissions: dict[str, AICapability] = Field(
        default_factory=dict,
        description="Map of user_id (str) -> AICapability for users in this tenant.",
    )


class TopupRequest(BaseModel):
    """POST /api/v1/admin/ai/credits/{tenant_id}/topup."""

    model_config = ConfigDict(extra="forbid")

    credits: int = Field(ge=1)
    notes: str | None = None


class PromptVersionInfo(BaseModel):
    """One version of a prompt — for the admin list view."""

    id: UUID
    name: str
    version: str
    is_active: bool
    model: str
    fallback_model: str | None
    temperature: float
    max_tokens: int
    description: str | None
    created_at: datetime
    archived_at: datetime | None


class PromptDetail(BaseModel):
    """Full prompt detail (text fields), for the editor view."""

    id: UUID
    name: str
    version: str
    is_active: bool
    system_text: str
    user_context_template: str | None
    assistant_prime: str | None
    model: str
    fallback_model: str | None
    temperature: float
    max_tokens: int
    cache_strategy: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class PromptCreate(BaseModel):
    """POST /api/v1/admin/ai/prompts — cria prompt novo (vira v1).

    Para um nome ja existente, use o endpoint de update (cria nova versao).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=128, pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")
    system_text: str = Field(min_length=10)
    user_context_template: str | None = None
    assistant_prime: str | None = None
    model: str = Field(min_length=1, max_length=64)
    fallback_model: str | None = None
    temperature: float = Field(ge=0.0, le=2.0, default=0.30)
    max_tokens: int = Field(ge=1, le=128_000, default=2048)
    cache_strategy: str = Field(default="after_system", pattern=r"^(none|after_system)$")
    description: str | None = None


class PromptUpdate(BaseModel):
    """PUT /api/v1/admin/ai/prompts/{id} — cria nova versao.

    Versao base e imutavel: este endpoint sempre cria uma nova versao
    (`v(N+1)`) copiando os campos atuais e aplicando os patches abaixo.
    """

    model_config = ConfigDict(extra="forbid")

    system_text: str | None = None
    user_context_template: str | None = None
    assistant_prime: str | None = None
    model: str | None = None
    fallback_model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=128_000)
    cache_strategy: str | None = Field(default=None, pattern=r"^(none|after_system)$")
    description: str | None = None


class PromptActivate(BaseModel):
    """PUT /api/v1/admin/ai/prompts/{name}/active — flip active version.

    Body recebe o id da versao a ativar (deve ser do mesmo `name`).
    """

    model_config = ConfigDict(extra="forbid")

    version_id: UUID


class PromptPreviewRequest(BaseModel):
    """POST /api/v1/admin/ai/prompts/{id}/preview — render sem chamar LLM."""

    model_config = ConfigDict(extra="forbid")

    context: dict[str, str] = Field(default_factory=dict)


class PromptPreviewResponse(BaseModel):
    """Output do preview — messages list pronta para enviar ao adapter."""

    name: str
    version: str
    model: str
    temperature: float
    max_tokens: int
    messages: list[dict]
