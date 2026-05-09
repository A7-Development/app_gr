"""wh_serasa_pj_business_reference -- capacidade de compra (referenciada por fornecedores)."""

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


class SerasaPjBusinessReference(Auditable, Base):
    """Capacidade de compra reportada por fornecedores.

    Vem de `advancedCommercialPaymentHistory.businessReferences` (raiz)
    + paths em `segmentData.{drawee,assignor}.businessReferences`.
    Carrega faixa de valor potencial total + faixa intermediaria
    (mid-range) anonimizadas (Serasa nao expoe valor exato).

    Observado tipico: "ULTIMA COMPRA" em "100 MIL A 200 MIL", mid-range
    "45 MIL A 47 MIL" — base pra dimensionar ticket medio da empresa.
    """

    __tablename__ = "wh_serasa_pj_business_reference"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_business_reference",
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
    business_description: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    reference_year: Mapped[str | None] = mapped_column(
        String(4), nullable=True
    )
    # Vem como "4" (numerico string) na raiz e "FEBRUARY"/"MARCH" (texto
    # extenso em ingles) nos sub-segmentos drawee/assignor. Largo o
    # suficiente pra ambos formatos.
    reference_month: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )

    # Faixa de valor potencial total.
    potential_value_range_code: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    potential_value_range_description: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    potential_value_from: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    potential_value_to: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )

    # Faixa intermediaria (mid-range — refinamento do valor potencial).
    potential_midrange_code: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    potential_midrange_description: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    potential_midrange_value_from: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    potential_midrange_value_to: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
