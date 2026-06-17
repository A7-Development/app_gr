"""Pydantic schemas (DTOs) para endpoints de /admin/ia/agents.

AgentDefinition = composto persona + expertises + prompt + modelo +
governance que define um agente Strata (CLAUDE.md §19.12).

Endpoints REST (em `app/modules/admin/api/ai_agent_definitions.py`):
    GET    /admin/ia/agents              lista (com is_active + usage)
    GET    /admin/ia/agents/{id}         detalhe (com persona/expertises/prompt expandidos)
    POST   /admin/ia/agents              cria nova familia (vira v1, ativa)
    PUT    /admin/ia/agents/{id}         cria nova versao copiando + patches
    PUT    /admin/ia/agents/{name}/active  promove versao
    POST   /admin/ia/agents/{id}/archive   soft-delete
    POST   /admin/ia/agents/{id}/preview   renderiza system_text composto (XML)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ─── Sub-objetos pra Detail/Preview (expansoes) ───────────────────────────


class AgentPersonaRef(BaseModel):
    """Resumo de persona referenciada (id + name + display + version)."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    display_name: str
    version: int


class AgentExpertiseRef(BaseModel):
    """Resumo de expertise referenciada."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    display_name: str
    domain: str
    version: int


class AgentPromptRef(BaseModel):
    """Resumo de prompt referenciado."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    version: str  # ai_prompt.version e string "v1", "v2"


# ─── Read DTOs ────────────────────────────────────────────────────────────


class AgentDefinitionVersionInfo(BaseModel):
    """Linha enxuta pra listagens."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    # Codigo curto/discreto derivado do nome (ex.: AGT-3F9A2C). Estavel por
    # familia; pra rastreabilidade na UI sem expor o nome interno.
    code: str
    name: str
    version: int
    # Quantas versoes a familia (name) tem. A lista mostra 1 linha por agente
    # (versao ATIVA como representante); versoes sao detalhe da aba Versoes.
    version_count: int = 1
    module: str
    persona_name: str | None = None  # resolved at server
    expertise_count: int = 0
    prompt_name: str
    model: str | None = None  # override; None = catalog default
    is_active: bool
    cross_module: bool
    tenant_id: UUID | None  # NULL = global
    created_at: datetime
    archived_at: datetime | None = None


class AgentDefinitionDetail(BaseModel):
    """Detalhe completo de uma versao — usado no editor."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str  # codigo curto derivado do nome (ver AgentDefinitionVersionInfo)
    name: str
    version: int
    module: str
    persona: AgentPersonaRef | None = None
    expertises: list[AgentExpertiseRef] = []
    prompt: AgentPromptRef | None = None  # None se prompt_name nao existe (raro)
    prompt_name: str  # raw — pra editor mostrar mesmo se prompt nao foi resolvido
    model: str | None = None
    fallback_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    cross_module: bool
    # None = usa default do CATALOG (spec.tools); [] = sem tools; [...] = override.
    allowed_tools: list[str] | None = None
    credit_hint: int | None = None
    tenant_id: UUID | None
    is_active: bool
    created_at: datetime
    archived_at: datetime | None = None


# ─── Write DTOs ───────────────────────────────────────────────────────────


class AgentDefinitionCreate(BaseModel):
    """Cria nova familia de agente. Vira v1 e e ativada automaticamente."""

    model_config = ConfigDict(extra="forbid")

    # Convencao canonica: <modulo>.<nome>, lowercase + dots + underscores.
    name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9]+(\.[a-z0-9_]+)*$",
    )
    module: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9_]+$",
    )
    persona_id: UUID | None = None
    expertise_ids: list[UUID] | None = None
    prompt_name: str = Field(min_length=1, max_length=128)
    model: str | None = None
    fallback_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    cross_module: bool = False
    # None = herda default do CATALOG; [] = sem tools; [...] = override explicito.
    allowed_tools: list[str] | None = None
    credit_hint: int | None = None


class AgentDefinitionUpdate(BaseModel):
    """Cria nova versao. Campos nao informados sao herdados da base.

    A nova versao NAO e ativada automaticamente.
    """

    model_config = ConfigDict(extra="forbid")

    persona_id: UUID | None = None
    expertise_ids: list[UUID] | None = None
    prompt_name: str | None = None
    model: str | None = None
    fallback_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    cross_module: bool | None = None
    # Em update, None = herda da base (nao mexe); [] = zera tools; [...] = override.
    allowed_tools: list[str] | None = None
    credit_hint: int | None = None


class AgentDefinitionActivate(BaseModel):
    """Promove uma versao a ativa pra `name`."""

    model_config = ConfigDict(extra="forbid")
    version_id: UUID


# ─── Preview ──────────────────────────────────────────────────────────────


class AgentDefinitionPreviewResponse(BaseModel):
    """Resultado do preview — renderiza o system_text composto que seria
    enviado ao LLM em runtime, exatamente como `compose_system_text` produz.

    Util pra debug: voce ve o XML final antes de ativar a versao.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    version: int
    system_text: str  # bloco XML completo (<persona>...<expertise>...<task>...)
    persona_full_id: str | None = None
    expertise_full_ids: list[str] = []
    prompt_full_id: str
    model: str
    fallback_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


# ─── Stats / telemetria (Fatia B) ───────────────────────────────────────────
#
# Uso REAL do agente, agregado de `agent_analysis_run` (a unica fonte com
# atribuicao por agente — `ai_usage_event` nao carrega agent_id). Agregado
# por `agent_name` (familia de versoes) e cross-tenant (visao do system
# maintainer). Read-only.


class AgentStatsByModel(BaseModel):
    """Quebra de uso por modelo."""

    model: str
    runs: int
    tokens_total: int
    cost_brl: float


class AgentRunRecent(BaseModel):
    """Uma execucao recente (linha da lista de runs)."""

    version: int
    model_used: str
    status: str
    tokens_input: int
    tokens_output: int
    tokens_cache_read: int
    tokens_cache_creation: int
    cost_brl: float | None
    duration_ms: int | None
    triggered_at: datetime


class AgentUsageOverviewRow(BaseModel):
    """Uso agregado de UM agente, para o ranking power-law do catalogo.

    Por `agent_name` (familia), cross-tenant. Lição central do relatório
    Prosus: ~2% dos agentes geram impacto desproporcional — este ranking
    ajuda a achar em quem dobrar a aposta (e o que nunca roda)."""

    agent_name: str
    total_runs: int
    window_runs: int
    runs_error: int
    cost_brl_total: float
    cost_brl_window: float
    tokens_total: int
    last_run_at: datetime | None


class AgentStatsResponse(BaseModel):
    """Telemetria de uso de um agente (aba Uso do cockpit)."""

    agent_name: str
    window_days: int

    # Histórico completo (all-time)
    total_runs: int
    runs_success: int
    runs_error: int
    runs_partial: int
    tokens_input: int
    tokens_output: int
    tokens_cache_read: int
    tokens_cache_creation: int
    cost_brl_total: float
    avg_duration_ms: float | None
    last_run_at: datetime | None

    # Janela (ultimos `window_days`)
    window_runs: int
    window_cost_brl: float
    window_tokens_total: int

    by_model: list[AgentStatsByModel]
    recent_runs: list[AgentRunRecent]
