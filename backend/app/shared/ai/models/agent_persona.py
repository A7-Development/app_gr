"""AgentPersona — papel reutilizavel injetado no system prompt (CLAUDE.md §19.12).

Persona define **QUEM** o agente e: papel, voz, autoridade, rigor analitico.
Reutilizavel entre agentes do mesmo papel ("Controller Senior" pode servir
multiplos agentes de controladoria).

Versionamento espelha `ai_prompt` + `ai_prompt_active`:
- Tabela base imutavel: `(name, version) UNIQUE`. Toda edicao cria nova versao.
- `agent_persona_active` aponta para a versao em producao (1 UPDATE = rollback).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AgentPersona(Base):
    """Definicao versionada de persona.

    `name` segue convencao `<area>.<papel>` (ex.: `credito.analista_senior`,
    `controladoria.controller_senior`). `version` comeca em 1 e incrementa
    a cada edicao. Versao base nunca muda (preserva audit trail).

    `role_block` e o texto markdown injetado no system prompt do agente.
    Mantenha curto (~100-300 tokens) — persona define identidade, nao
    conhecimento (esse vai em AgentExpertise).
    """

    __tablename__ = "agent_persona"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_agent_persona_name_version"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role_block: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Tags livres para curador (ex.: ["credito", "contabilidade"]).
    expertise_domains: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )

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
        return f"<AgentPersona {self.name}@v{self.version}>"

    @property
    def full_id(self) -> str:
        """Identificador legivel para logs/audit (espelha Prompt.full_id)."""
        return f"{self.name}@v{self.version}"


class AgentPersonaActive(Base):
    """Aponta para a versao ativa de cada `agent_persona.name`.

    Rollback de 1 click sem deploy: UPDATE da `persona_id` para apontar
    outra versao. Espelha `ai_prompt_active`.
    """

    __tablename__ = "agent_persona_active"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    persona_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_persona.id"),
        nullable=False,
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    activated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<AgentPersonaActive {self.name} -> {self.persona_id}>"
