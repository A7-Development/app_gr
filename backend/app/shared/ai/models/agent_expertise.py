"""AgentExpertise — knowledge pack injetado no system prompt (CLAUDE.md §19.12).

Expertise define **O QUE O AGENTE SABE**: embasamento teorico aplicado,
vocabulario tecnico, heuristicas profissionais, referencias regulatorias.

Granularidade inicial: **grossa** (1 papel ~ 1 expertise, ex.: "Contador FIDC",
"Analista de Credito"). Pode subdividir depois sem dor — split via nova
expertise + agentes apontam pra ambas (`expertise_ids` e array).

Versionamento espelha `ai_prompt` / `agent_persona`: `(name, version) UNIQUE`
+ active pointer pra rollback de 1 click.

Hoje: `knowledge_text` e markdown concatenado direto no system prompt do
agente. Quando exceder ~3k tokens por expertise, vira RAG via pgvector
(coluna `embedding` adicionada conforme demanda).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AgentExpertise(Base):
    """Definicao versionada de expertise (knowledge pack).

    `name` segue convencao `<dominio>.<topico>` (ex.: `contabilidade.fidc`,
    `regulatorio.cmn_4966`, `credito.analise_dossie`).

    `knowledge_text` e markdown — suporta headers, listas, tabelas, codigo,
    links. Vai concatenado no system prompt do agente (entre persona e
    prompt task).
    """

    __tablename__ = "agent_expertise"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_agent_expertise_name_version"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    knowledge_text: Mapped[str] = mapped_column(Text, nullable=False)
    # [{url, label, kind: "norma"|"doc"|"link"}, ...]
    reference_urls: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
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
        return f"<AgentExpertise {self.name}@v{self.version} domain={self.domain}>"

    @property
    def full_id(self) -> str:
        return f"{self.name}@v{self.version}"


class AgentExpertiseActive(Base):
    """Aponta para a versao ativa de cada `agent_expertise.name`."""

    __tablename__ = "agent_expertise_active"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    expertise_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_expertise.id"),
        nullable=False,
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    activated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<AgentExpertiseActive {self.name} -> {self.expertise_id}>"
