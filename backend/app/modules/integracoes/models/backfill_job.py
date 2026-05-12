"""BackfillJob: coordena backfill assincrono de N datas pra 1 endpoint.

Criado em 2026-05-12 pra suportar "bulk implicito" no heatmap de cobertura
+ one-shot scan na ativacao da Fase 3 (ver project_qitech_freshness_followups
memory pra contexto completo).

Granularidade: 1 job por (tenant, endpoint). Click em "Backfill outros-fundos"
cria 1 job. Click em "Backfill cpr" cria outro. Worker processa serialmente
dentro do job, mas jobs distintos podem rodar em paralelo (limitado pelo
APScheduler max_instances).

Estados (status):
    pending    — recem-criado, ainda nao pegou pelo worker
    running    — worker iniciou processamento
    done       — todas as datas processadas (com sucesso ou falha individual)
    failed     — erro nao-recuperavel (config invalida, etc); para sem
                 completar todas as datas
    cancelled  — operador cancelou via UI antes/durante execucao

Datas individuais sao tracked em 3 arrays:
    dates_pending   — ainda nao tentadas
    dates_done      — sucesso (sync retornou ok)
    dates_failed    — falha individual; jsonb com {date, error} pra exibir
                      na UI sem perder qual data deu qual problema
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class BackfillJob(Base):
    """Backfill assincrono de N datas pra 1 endpoint de uma source."""

    __tablename__ = "backfill_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed', 'cancelled')",
            name="ck_backfill_job_status",
        ),
        Index("ix_backfill_job_tenant_status", "tenant_id", "status"),
        Index(
            "ix_backfill_job_endpoint",
            "tenant_id",
            "source_type",
            "endpoint_name",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    endpoint_name: Mapped[str] = mapped_column(String(128), nullable=False)

    dates_pending: Mapped[list[date]] = mapped_column(
        ARRAY(Date), nullable=False
    )
    dates_done: Mapped[list[date]] = mapped_column(
        ARRAY(Date), nullable=False, server_default=text("'{}'::date[]")
    )
    dates_failed: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BackfillJob id={self.id} endpoint={self.endpoint_name} "
            f"status={self.status} pending={len(self.dates_pending)} "
            f"done={len(self.dates_done)} failed={len(self.dates_failed)}>"
        )
