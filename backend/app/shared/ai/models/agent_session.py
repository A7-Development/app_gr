"""AgentSession + AgentSessionStep — persistencia da memoria de sessao (sec 19.11).

Tabelas append-only que recebem o flush hibrido da `AnalysisSession`:
quando uma sessao passa de 60s OU e finalizada (end_session()), a
camada `app/agentic/memory/persistence.py` copia steps + scratchpad
final pra ca.

Isolamento (regra dura, CLAUDE.md sec 10):
    `tenant_id NOT NULL` em ambas. Toda query sobre estas tabelas
    precisa filtrar por tenant_id antes de qualquer outra coisa.

Particionamento:
    Tabelas comuns no MVP. Quando o volume justificar (estimativa:
    ~1M rows em 1 ano), particionar `agent_session_step` por
    (tenant_id, iso_at) range mensal.
"""

from __future__ import annotations

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AgentSession(Base):
    """Sessao de analise agentica — agrupa N invocacoes de agente."""

    __tablename__ = "agent_session"
    __table_args__ = (
        Index(
            "ix_agent_session_tenant_started",
            "tenant_id",
            "started_at",
            postgresql_ops={"started_at": "DESC"},
        ),
        Index(
            "ix_agent_session_context_label",
            "tenant_id",
            "context_label",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    started_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Modulo de origem da invocacao (BI, CREDITO, etc). 32 chars cobre
    # qualquer valor do enum Module com folga.
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    # Rotulo legivel ('dossier:abc-123', 'chat:conv-456',
    # 'workflow:def-id:run-id'). Indexado pra busca direta.
    context_label: Mapped[str] = mapped_column(String(256), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Snapshot do scratchpad em end_session(). NULL quando sessao termina
    # sem nada escrito (caso normal pra session com 1 agente unico).
    scratchpad_final: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Denormalized count — atualizado pela persistence layer no flush
    # final. Permite paginar sessions sem COUNT(*) caro em
    # agent_session_step.
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AgentSessionStep(Base):
    """Step individual append-only dentro de uma AgentSession.

    Shape espelha `SessionStep` in-memory (CLAUDE.md sec 19.11). O
    persistence layer (C3) faz INSERT por step quando o flush dispara.
    """

    __tablename__ = "agent_session_step"
    __table_args__ = (
        # step_index e monotonic dentro de uma session (atribuido in-memory
        # antes do flush). UQ protege contra duplo-flush.
        UniqueConstraint(
            "session_id",
            "step_index",
            name="uq_agent_session_step_session_index",
        ),
        Index(
            "ix_agent_session_step_tenant_iso",
            "tenant_id",
            "iso_at",
            postgresql_ops={"iso_at": "DESC"},
        ),
        Index(
            "ix_agent_session_step_session",
            "session_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Rotulo curto do agente ('credito.financial_analyst@v1'). NULL para
    # steps sistemicos (record_observation sem agente associado).
    agent_full_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    iso_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Enum StepKind como string: tool_use, tool_result, scratchpad,
    # observation, error. Sem enum DB explicito — facilita add de novos
    # kinds sem migration.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
