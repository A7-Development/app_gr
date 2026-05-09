"""wh_serasa_pj_pagamento_evolucao_mensal -- serie temporal de compromissos."""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class SerasaPjPagamentoEvolucaoMensal(Auditable, Base):
    """Evolucao mensal de compromissos comerciais (faixas anonimizadas).

    Vem de `advancedCommercialPaymentHistory.evolutionCommitmentsSuppliers
    .evolutionCommitmentsSuppliersList[]` (raiz + paths em segmentData
    sub-segmentos drawee/assignor).

    Tipico: 13 meses (mes corrente + 12 anteriores). Cada linha tras
    faixa de valor de "compromissos a vencer" + "compromissos vencidos"
    no mes — base pra modelo de credito B2B observar tendencia.
    """

    __tablename__ = "wh_serasa_pj_pagamento_evolucao_mensal"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_pagamento_evolucao_mensal",
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
    consulta_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_serasa_pj_consulta.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    segment_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    year_commitment: Mapped[str | None] = mapped_column(
        String(4), nullable=True
    )
    # Vem "4" na raiz e nomes textuais ("FEBRUARY", "MARCH") nos
    # sub-segmentos. Largo pra ambos.
    month_commitment: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    month_description: Mapped[str | None] = mapped_column(
        String(8), nullable=True
    )
    segment_information: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )

    # Total do mes (compromissos + atrasos).
    total_month_range_code: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    total_month_range_description: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    total_monthly_range_value_from: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    total_monthly_range_value_to: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )

    # Compromissos a vencer no mes.
    value_commitments_due_from: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    value_commitments_due_to: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    track_code_to_expire: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    track_description_to_expire: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    # Compromissos vencidos (atraso) no mes.
    value_overdue_commitments_from: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    value_overdue_commitments_to: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    expired_track_code: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    expired_track_description: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
