"""wh_cpr_movimento -- Contas a Pagar e Receber do FIDC.

Despesas estruturadas (auditoria, custodia, taxa CVM, etc) e receitas
diferidas. Granularidade: 1 linha por (tenant, data, hash do item).
QiTech NAO devolve id estavel — UQ via sha16 do item completo.

Fonte: QiTech `/v2/netreport/report/market/cpr/{data}`.
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
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class CprMovimento(Auditable, Base):
    """Movimento de CPR (Contas a Pagar e Receber) do FIDC."""

    __tablename__ = "wh_cpr_movimento"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_cpr_movimento"),
        Index("ix_wh_cpr_movimento_tenant_data", "tenant_id", "data_posicao"),
        Index(
            "ix_wh_cpr_movimento_tenant_carteira",
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
    # UA dona da credencial que produziu esta linha (multi-UA, Phase F).
    # Nullable apenas para retrocompat com linhas legacy ingeridas antes
    # da introducao de multi-UA. Toda nova linha gravada pelo adapter
    # informa explicitamente.
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "cadastros_unidade_administrativa.id", ondelete="RESTRICT"
        ),
        nullable=True,
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

    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    historico_traduzido: Mapped[str] = mapped_column(Text, nullable=False)

    # Despesa = negativo, receita = positivo. Diferimentos podem ser positivos.
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # `percentualSobreCpr` vem com 8 casas (-2.0387403). Numeric(12,8).
    percentual_sobre_cpr: Mapped[Decimal] = mapped_column(
        Numeric(12, 8), nullable=False
    )
    percentual_sobre_total: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )
