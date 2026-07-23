"""Schemas Pydantic do CRUD admin de Servidores MCP (spec copiloto-mcp §7).

Espelham o padrao versionado de agent_definition: edicao cria nova versao;
ativacao e um ponteiro. Credencial NUNCA aparece — so o `credential_id`
(FK pro store cifrado `provedor_dados_credencial`).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class McpServerBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=8, max_length=255)
    transport: str = Field(default="http", pattern="^(http|stdio)$")
    module: str | None = None
    credential_id: UUID | None = None
    auth_header_map: dict[str, str] | None = None
    allowed_tools: list[str] | None = None
    mode: str = Field(default="ephemeral", pattern="^(ephemeral|materialized)$")
    cost_hint: str = Field(default="expensive", pattern="^(cheap|medium|expensive)$")
    max_calls_per_turn: int = Field(default=5, ge=1, le=50)
    tool_result_max_chars: int = Field(default=20000, ge=1000, le=200000)
    description: str | None = None


class McpServerCreate(McpServerBase):
    """POST /admin/ia/mcp — cria v1 e ativa."""

    name: str = Field(min_length=2, max_length=64, pattern="^[a-z0-9_-]+$")


class McpServerUpdate(BaseModel):
    """PUT /admin/ia/mcp/{id} — copia a base + patches -> NOVA versao (nao ativa)."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, min_length=8, max_length=255)
    transport: str | None = Field(default=None, pattern="^(http|stdio)$")
    module: str | None = None
    credential_id: UUID | None = None
    auth_header_map: dict[str, str] | None = None
    allowed_tools: list[str] | None = None
    mode: str | None = Field(default=None, pattern="^(ephemeral|materialized)$")
    cost_hint: str | None = Field(default=None, pattern="^(cheap|medium|expensive)$")
    max_calls_per_turn: int | None = Field(default=None, ge=1, le=50)
    tool_result_max_chars: int | None = Field(default=None, ge=1000, le=200000)
    description: str | None = None


class McpServerDetail(BaseModel):
    """Uma versao de servidor MCP (row de mcp_server)."""

    id: UUID
    tenant_id: UUID | None
    name: str
    version: int
    url: str
    transport: str
    module: str | None
    credential_id: UUID | None
    auth_header_map: dict[str, str] | None
    allowed_tools: list[str] | None
    mode: str
    cost_hint: str
    max_calls_per_turn: int
    tool_result_max_chars: int
    description: str | None
    created_at: datetime
    archived_at: datetime | None
    is_active: bool


class McpServerActivate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int


class McpProbeResponse(BaseModel):
    """Resultado do botao 'Testar conexao' (initialize + tools/list, sem custo)."""

    ok: bool
    tool_count: int = 0
    allowed_count: int = 0
    error: str | None = None
