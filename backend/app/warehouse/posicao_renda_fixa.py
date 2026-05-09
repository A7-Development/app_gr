"""wh_posicao_renda_fixa -- posicao em titulos de renda fixa.

CDB, debentures, NTN-B, etc. Granularidade: 1 linha por (tenant, data,
codigo, cliente). Sample REALINVEST tem 26 titulos com 3 indexadores
(CDI, IPCA, PRE).

Fonte: QiTech `/v2/netreport/report/market/rf/{data}`.

Indice extra `(tenant_id, cnpj_emitente, data_posicao)` -> drill-down
"exposicao por emitente" (concentracao de risco).
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


class PosicaoRendaFixa(Auditable, Base):
    """Posicao em RF (CDB/debenture/NTN-B/...) numa data."""

    __tablename__ = "wh_posicao_renda_fixa"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_posicao_renda_fixa"
        ),
        Index(
            "ix_wh_posicao_renda_fixa_tenant_data",
            "tenant_id",
            "data_posicao",
        ),
        Index(
            "ix_wh_posicao_renda_fixa_tenant_carteira",
            "tenant_id",
            "carteira_cliente_doc",
            "data_posicao",
        ),
        Index(
            "ix_wh_posicao_renda_fixa_tenant_emitente",
            "tenant_id",
            "cnpj_emitente",
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

    # -- Carteira --
    carteira_cliente_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    carteira_cliente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    carteira_cliente_doc: Mapped[str] = mapped_column(
        String(14), nullable=False, index=True
    )

    # -- Ativo --
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    nome_do_papel: Mapped[str] = mapped_column(String(100), nullable=False)
    emitente: Mapped[str] = mapped_column(String(100), nullable=False)
    cnpj_emitente: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    codigo_lastro: Mapped[str] = mapped_column(String(50), nullable=False)
    indexador: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # -- Datas --
    data_da_emissao: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_aplicacao: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_vencimento_lastro: Mapped[date | None] = mapped_column(Date, nullable=True)

    # -- Flags / classificacao --
    origem: Mapped[str | None] = mapped_column(String(4), nullable=True)
    operacao_a_termo: Mapped[str | None] = mapped_column(String(4), nullable=True)
    # `negociação/vencimento` -- vem null no sample. String pra futura compatibilidade.
    negociacao_vencimento: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # -- Fatos: taxas (8 decimais) --
    taxa_mtm: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    taxa_over: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    taxa_ano: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)

    # -- Fatos: quantidade e PU --
    # Quantidade pode ser negativa (resgate / venda).
    quantidade: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    pu_mercado: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)

    # -- Fatos: valores monetarios --
    valor_aplicado: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_resgate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # valor_bruto pode ser negativo (resgate alem do aplicado).
    valor_bruto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_impostos: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_liquido: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    percentual_sobre_rf: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )
    percentual_sobre_total: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )

    # `mtm` aparece null no sample (semantica indefinida — pode ser data
    # ou rotulo). Mantido como string ate observar dado real preenchido.
    mtm: Mapped[str | None] = mapped_column(String(50), nullable=True)
