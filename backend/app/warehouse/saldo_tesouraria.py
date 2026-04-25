"""wh_saldo_tesouraria -- saldo em tesouraria do FIDC por classe de cota.

Granularidade: 1 linha por (tenant_id, data_posicao, carteira_cliente_id,
descricao_slug). Re-ingerir o mesmo dia substitui via UQ
(tenant_id, source_id).

Fonte: QiTech `/v2/netreport/report/market/tesouraria/{data}`.

Sample: 1 linha por classe de cota — REALINVEST, REALINVEST MEZ,
REALINVEST SEN — todas com `descricao = "Saldo em Tesouraria"`. A
discriminacao vem do `clienteId`.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class SaldoTesouraria(Auditable, Base):
    """Saldo em tesouraria por classe de cota num data."""

    __tablename__ = "wh_saldo_tesouraria"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_saldo_tesouraria"),
        Index("ix_wh_saldo_tesouraria_tenant_data", "tenant_id", "data_posicao"),
        Index(
            "ix_wh_saldo_tesouraria_tenant_carteira",
            "tenant_id",
            "carteira_cliente_doc",
            "data_posicao",
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

    data_posicao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    carteira_cliente_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    carteira_cliente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    carteira_cliente_doc: Mapped[str] = mapped_column(
        String(14), nullable=False, index=True
    )

    descricao: Mapped[str] = mapped_column(String(200), nullable=False)

    # Saldo pode ser zero ou negativo (raro mas possivel).
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    percentual_sobre_cpr: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )
    percentual_sobre_total: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )
