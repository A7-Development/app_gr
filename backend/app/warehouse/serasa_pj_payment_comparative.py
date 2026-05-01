"""wh_serasa_pj_payment_comparative -- comparativo empresa vs mercado vs segmento."""

from uuid import UUID, uuid4

from sqlalchemy import (
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class SerasaPjPaymentComparative(Auditable, Base):
    """Comparativo mensal: empresa vs mercado geral vs segmento dela.

    Vem de `advancedCommercialPaymentHistory.segmentData.drawee
    .paymentHistoryComparativeAnalysis.paymentHistoryComparativeAnalysisList[]`.

    Cada linha = 1 mes com 2 perspectivas (market e segment), cada uma
    com codigo+descricao de pagamento spot e parcelado. Permite
    observar se a empresa paga melhor/pior que o mercado geral e que
    o segmento especifico dela.
    """

    __tablename__ = "wh_serasa_pj_payment_comparative"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_payment_comparative",
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
    month_label: Mapped[str] = mapped_column(String(10), nullable=False)

    # Market: comparativo com todo o mercado.
    market_origin_code: Mapped[str | None] = mapped_column(
        String(8), nullable=True
    )
    market_spot_payment_code: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    market_spot_payment_description: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    market_installment_payment_code: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    market_installment_payment_description: Mapped[str | None] = (
        mapped_column(String(64), nullable=True)
    )

    # Segment: comparativo com o segmento da empresa.
    segment_origin_code: Mapped[str | None] = mapped_column(
        String(8), nullable=True
    )
    segment_spot_payment_code: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    segment_spot_payment_description: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    segment_installment_payment_code: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    segment_installment_payment_description: Mapped[str | None] = (
        mapped_column(String(64), nullable=True)
    )
