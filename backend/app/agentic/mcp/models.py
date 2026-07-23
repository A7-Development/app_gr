"""McpServer + McpServerActive — catalogo DB-first de Servidores MCP.

Espelha o padrao `agent_definition`/`_active` (spec copiloto-mcp §4.2):
`(name, version)` imutavel; edicao = nova versao; active pointer por
`(tenant_id, name)` com rollback de 1 UPDATE. `tenant_id NULL` = servidor
global (BDC hoje).

Credencial NAO mora aqui: `credential_id` referencia o store cifrado
EXISTENTE `provedor_dados_credencial` (um segredo = um ponto de rotacao).
O mapeamento payload->headers e config (`auth_header_map`), nao codigo
de vendor.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class McpTransport(enum.StrEnum):
    """Transporte do servidor MCP."""

    HTTP = "http"      # Streamable HTTP (unico suportado hoje)
    STDIO = "stdio"    # futuro


class McpMode(enum.StrEnum):
    """Contrato de persistencia do dado do MCP (spec §2.6)."""

    EPHEMERAL = "ephemeral"        # so LLM — dado do vendor nao persiste
    MATERIALIZED = "materialized"  # futuro: mapper -> silver


class McpServer(Base):
    """Um Servidor MCP registrado (versao imutavel)."""

    __tablename__ = "mcp_server"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_mcp_server_name_version"),
        Index("ix_mcp_server_tenant_name", "tenant_id", "name"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # NULL = global (curado pela Strata); preenchido = custom de tenant (futuro).
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    url: Mapped[str] = mapped_column(String(255), nullable=False)
    transport: Mapped[McpTransport] = mapped_column(
        SAEnum(McpTransport, name="mcp_transport", native_enum=False, length=16),
        nullable=False,
        default=McpTransport.HTTP,
    )

    # Tag de escopo (CLAUDE.md §11.1): NULL = cross-module. Determina qual
    # permissao de modulo gateia o servidor no cardapio (spec §5.2).
    module: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    # -> provedor_dados_credencial (store cifrado existente, spec §4.2).
    # NULL = servidor sem auth.
    credential_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provedor_dados_credencial.id"),
        nullable=True,
    )
    # Mapeia chaves do payload decifrado -> nomes de header HTTP.
    # Ex. BDC: {"access_token": "AccessToken", "token_id": "TokenId"}.
    # Payload com shape {"headers": {...}} dispensa o mapa (usado direto).
    auth_header_map: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )

    # Allowlist dos nomes de tool do MCP (ex.: 10 de credito, nao as 166).
    # NULL = todas as tools do servidor (evitar em vendor pago).
    allowed_tools: Mapped[list | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )

    mode: Mapped[McpMode] = mapped_column(
        SAEnum(McpMode, name="mcp_mode", native_enum=False, length=16),
        nullable=False,
        default=McpMode.EPHEMERAL,
    )
    cost_hint: Mapped[str] = mapped_column(
        String(16), nullable=False, default="expensive", server_default="expensive"
    )

    # Guard-rails de custo/tamanho, enforced no executor (spec §6.4).
    max_calls_per_turn: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )
    tool_result_max_chars: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20000, server_default="20000"
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        scope = f"tenant={self.tenant_id}" if self.tenant_id else "global"
        return f"<McpServer {self.name}@v{self.version} {scope} mode={self.mode.value}>"


class McpServerActive(Base):
    """Aponta a versao ativa de cada `(tenant_id, name)` — rollback 1 UPDATE."""

    __tablename__ = "mcp_server_active"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_mcp_server_active_tenant_name"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mcp_server.id"), nullable=False
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    activated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        scope = f"tenant={self.tenant_id}" if self.tenant_id else "global"
        return f"<McpServerActive {scope} {self.name} -> {self.server_id}>"
