"""Cedente-level risk spine: per-indicator snapshots + versioned composition.

The decision unit of a FIDC is the CEDENTE (visao Ricardo 2026-07-08): each
detection model in the `deteccao_modelo` catalog is ONE INDICATOR that
contributes a subscore; the panel composes them into a single Cedente Risk.
Today N=1 (liquidacao_boleto); Benford, lastro, concentracao and the graph
models join as NEW ROWS per cedente — zero panel refactor.

Design:
    - `cedente_risco_snapshot` is a TIME SERIES (one row per cedente x
      indicator x data_ref): trend ("piorou este mes") and early-warning
      need history, so we snapshot instead of computing live. modelo_id NULL
      = the COMPOSITE row (UNIQUE NULLS NOT DISTINCT guards it).
    - `cedente_risco_composicao` is the versioned combination formula
      (premise_set pattern): weights per indicator editable without deploy;
      likely replaced by a trained meta-model when there are enough
      indicators — the SHAPE accepts that future.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class CedenteRiscoSnapshot(Base):
    """Subscore of one indicator (or the composite) for one cedente on a date."""

    __tablename__ = "cedente_risco_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "cedente_documento",
            "modelo_id",
            "data_ref",
            name="uq_cedente_risco_snapshot",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    cedente_documento: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    cedente_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # NULL = linha do RISCO COMPOSTO do cedente (combinacao dos indicadores).
    modelo_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("deteccao_modelo.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    data_ref: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # 0-100. v1 do indicador de liquidacao: 100 * (R$ em eventos de score
    # >= 0.7 / R$ avaliado), com piso 70 quando ha padrao critico — monetario
    # e explicavel; a formula evolui com versoes da composicao.
    subscore: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    valor_avaliado: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    valor_em_risco: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    n_eventos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    n_criticos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    n_alto_risco: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Decomposicao explicavel (§14.3): componentes da conta + versao usada.
    componentes: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<CedenteRiscoSnapshot {self.cedente_documento} "
            f"{self.data_ref} score={self.subscore}>"
        )


class CedenteRiscoComposicao(Base):
    """Versioned weights of the composite (append-only; active = max version)."""

    __tablename__ = "cedente_risco_composicao"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_cedente_risco_composicao"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # {"liquidacao_boleto": 1.0, ...} — pesos normalizados na aplicacao.
    pesos: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False)
    justificativa: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<CedenteRiscoComposicao v{self.version} pesos={self.pesos}>"
