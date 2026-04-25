"""wh_posicao_compromissada -- operacao compromissada (overnight tipico).

Compromissada e RF de curtissimo prazo (geralmente overnight) — o FIDC
"empresta" pra contraparte e recebe de volta no dia seguinte. Schema
parecido com `wh_posicao_renda_fixa` mas SEM emitente/cnpj_emitente
(nao se aplica) e com pares dataAquisicao/dataResgate.

Granularidade: 1 linha por (tenant, data, codigo, cliente).

Fonte: QiTech `/v2/netreport/report/market/rf-compromissadas/{data}`.
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


class PosicaoCompromissada(Auditable, Base):
    """Posicao em operacao compromissada (overnight) num data."""

    __tablename__ = "wh_posicao_compromissada"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_posicao_compromissada"
        ),
        Index(
            "ix_wh_posicao_compromissada_tenant_data",
            "tenant_id",
            "data_posicao",
        ),
        Index(
            "ix_wh_posicao_compromissada_tenant_carteira",
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

    # Ativo: compromissada nao tem cnpjEmitente (sample em 2026-04-07)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    papel: Mapped[str] = mapped_column(String(100), nullable=False)

    # Datas chave: aquisicao -> resgate (dia seguinte tipicamente).
    data_aquisicao: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_resgate: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_emissao: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Fatos: taxas
    taxa_over: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    taxa_ano: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)

    # Fatos: quantidade / PU / valores
    quantidade: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    pu: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    valor_aplicado: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_resgate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_bruto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    percentual_sobre_rf: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )
    percentual_sobre_total: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )

    # `mtm` e `negociação/vencimento` aparecem null no sample.
    mtm: Mapped[str | None] = mapped_column(String(50), nullable=True)
    negociacao_vencimento: Mapped[str | None] = mapped_column(String(20), nullable=True)
