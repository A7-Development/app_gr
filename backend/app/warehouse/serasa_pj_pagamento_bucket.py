"""wh_serasa_pj_pagamento_bucket -- buckets de pontualidade comercial."""

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


class SerasaPjPagamentoBucket(Auditable, Base):
    """Bucket de faixa de pontualidade do `paymentHistory.titlesQuantity`.

    Cada bucket representa uma faixa de comportamento de pagamento da
    empresa (ex.: "PONTUAL", "ATE 30 DIAS"), com:
        - faixa textual e codigo
        - faixa de valores cobertos (rangeValueFrom/To)
        - faixa de % do total que cai no bucket (percentageFrom/To)

    Util pra modelo de credito B2B (proxy de capacidade de pagamento da
    empresa-alvo).
    """

    __tablename__ = "wh_serasa_pj_pagamento_bucket"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_pagamento_bucket",
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

    # Tipo do segmento (drawee/assignor/individual). No segmento 028
    # so vem `assignor` populado em factoring.
    segment_kind: Mapped[str] = mapped_column(String(16), nullable=False)

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    range_label: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    range_code: Mapped[str | None] = mapped_column(String(16), nullable=True)

    range_value_from: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    range_value_to: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )

    # Serasa envia percentuais em centesimos (basis points): 100% = 10000.
    # Numeric(8,4) (max 9999.9999) estourava no bucket PONTUAL de empresas
    # 100% pontuais (percentageTo=10000.0). Numeric(9,4) segura 10000.0000.
    percentage_from: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 4), nullable=True
    )
    percentage_to: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 4), nullable=True
    )
    percentage_label: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
