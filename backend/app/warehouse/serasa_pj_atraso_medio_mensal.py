"""wh_serasa_pj_atraso_medio_mensal -- atraso medio em dias por mes."""

from uuid import UUID, uuid4

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class SerasaPjAtrasoMedioMensal(Auditable, Base):
    """Atraso medio (em faixa de dias) por mes, por sub-segmento.

    Vem de `advancedCommercialPaymentHistory.segmentData.{drawee,
    assignor}.paymentHistory.averageDelayPeriod.periodList[]`. Cada
    linha tras a faixa de dias (from/to) que a empresa atrasa pagamentos
    em determinado mes.

    Util pra grafico de evolucao de pontualidade — empresa com atraso
    crescente nos ultimos meses e red flag.
    """

    __tablename__ = "wh_serasa_pj_atraso_medio_mensal"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_atraso_medio_mensal",
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
    # Formato Serasa: "ABR/25", "MAI/25", etc.
    month_label: Mapped[str] = mapped_column(String(10), nullable=False)
    average_delay_days_from: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    average_delay_days_to: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
