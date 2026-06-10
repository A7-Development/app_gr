"""wh_posicao_cedente(_produto) + wh_posicao_sacado — posicoes por papel (F1).

Snapshots consolidados que o Bitfin calcula por papel (ClientePosicao /
ClientePosicaoProduto / SacadoPosicao), normalizados e ancorados na entidade
canonica (`wh_entidade`). Alimentam os blocos Carteira Ativa, Limites
aprovados e Performance do EntidadePeek / Ficha da Entidade.

Sao numeros VENDOR-COMPUTED (janela de apuracao fixa, regras do Bitfin) —
proveniencia `erp:bitfin`. Quando a 2a plataforma chegar, estas metricas
ganham motor de calculo proprio sobre os primitivos canonicos (titulos +
liquidacoes) e passam a `derived` (decisao 2026-06-10).

Full refresh por sync (snapshot corrente; sem historico — serie temporal de
posicao e follow-up). `entidade_id` nullable: posicao de papel cuja entidade
esta em quarentena e preservada (nada some, §14.6 espirito).
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class _PosicaoLiquidezMixin:
    """Breakdown da liquidez (janela de apuracao do Bitfin) — comum a
    cedente e sacado. Os componentes somam `vencimentario_liquidez`."""

    indice_liquidez: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    vencimentario_liquidez: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    liquidez_qtde_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    liquidez_data_inicial: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    liquidez_data_final: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    liquidez_total_liquidados: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    liquidez_total_recomprados: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    liquidez_total_vencidos_penalizados: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    liquidez_total_vencidos_nao_penalizados: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    liquidez_data_apuracao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class _PosicaoRiscoMixin:
    """Risco em aberto (qtd + valor) — total / vencido / a vencer."""

    risco_total_qtd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risco_total_valor: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    risco_vencido_qtd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risco_vencido_valor: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    risco_avencer_qtd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risco_avencer_valor: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )


class WhPosicaoCedente(_PosicaoLiquidezMixin, _PosicaoRiscoMixin, Auditable, Base):
    """Posicao consolidada do papel CEDENTE (Bitfin ClientePosicao).

    source_id (Auditable) = PosicaoId do Bitfin. `papel_source_id` = ClienteId
    (mesma ponte de wh_operacao.cedente_id).
    """

    __tablename__ = "wh_posicao_cedente"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_type", "source_id", name="uq_wh_posicao_cedente"
        ),
        Index("ix_wh_posicao_cedente_entidade", "tenant_id", "entidade_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entidade_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_entidade.id", ondelete="SET NULL"),
        nullable=True,
    )
    papel_source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    prazo_medio_carteira: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4), nullable=True
    )


class WhPosicaoCedenteProduto(_PosicaoRiscoMixin, Auditable, Base):
    """Posicao do papel CEDENTE quebrada por produto (ClientePosicaoProduto).

    Carrega LIMITE OPERACIONAL + tranche — limite e conceito do papel cedente
    (decisao 2026-06-10: nao ha limite por sacado).
    source_id = "<PosicaoId>:<ProdutoId>".
    """

    __tablename__ = "wh_posicao_cedente_produto"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_type", "source_id",
            name="uq_wh_posicao_cedente_produto",
        ),
        Index("ix_wh_posicao_cedente_produto_entidade", "tenant_id", "entidade_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entidade_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_entidade.id", ondelete="SET NULL"),
        nullable=True,
    )
    papel_source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    produto_source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    produto_sigla: Mapped[str | None] = mapped_column(String(20), nullable=True)

    limite_operacional: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    tranche: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    indice_liquidez: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    hist_liquidacoes_qtd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hist_liquidacoes_valor: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    hist_baixados_qtd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hist_baixados_valor: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )


class WhPosicaoSacado(_PosicaoLiquidezMixin, _PosicaoRiscoMixin, Auditable, Base):
    """Posicao consolidada do papel SACADO (Bitfin SacadoPosicao, subset
    essencial — a tabela fonte tem ~120 colunas; ingerimos o nucleo de risco/
    liquidez/pontualidade; colunas adicionais entram por demanda da Ficha).

    source_id = PosicaoId. `papel_source_id` = SacadoId (ponte de
    wh_titulo.sacado_id).
    """

    __tablename__ = "wh_posicao_sacado"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_type", "source_id", name="uq_wh_posicao_sacado"
        ),
        Index("ix_wh_posicao_sacado_entidade", "tenant_id", "entidade_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entidade_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_entidade.id", ondelete="SET NULL"),
        nullable=True,
    )
    papel_source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    ticket_medio: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    indice_pontualidade: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4), nullable=True
    )
    prorrogados_qtd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prorrogados_valor: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    prazo_medio_prorrogacao: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4), nullable=True
    )
    hist_titulos_qtd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hist_titulos_valor: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    hist_liquidacoes_qtd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hist_liquidacoes_valor: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    hist_recompras_qtd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hist_recompras_valor: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
