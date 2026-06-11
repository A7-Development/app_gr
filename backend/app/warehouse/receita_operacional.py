"""wh_receita_operacional -- fato canonico de receita operacional CAIXA-FIEL.

Uma linha = um evento de receita que LIQUIDOU financeiramente (ou foi retido
do liquido na efetivacao da operacao), na granularidade
(stream, natureza, documento-origem). Materializado pelo ETL Bitfin a partir
do catalogo de streams (`wh_bitfin_receita_stream`), lendo as fontes nativas:

    Titulo                  -> mora paga na liquidacao (pgto - liquido)
    ContaCorrenteLancamento -> prorrogacao/cartorio/tarifas/repasses/financeira
    RecompraResultado/Item  -> juros/multa/desagio de recompra (Efetivada=1)
    OperacaoRentabilidade   -> desagio + tarifas de operacao (retidos na fonte)

NAO le DemonstrativoDeResultado (DRE comercial = mora TEORICA, decisao
2026-06-10). A DRE permanece como visao comercial separada em wh_dre_mensal;
o gap entre as duas e a regua de superestimacao da apuracao comercial.

Governanca (zero chute):
- `stream_key` NULL = lancamento em codigo de RECEITA sem stream ativo no
  catalogo -- "nao classificado", visivel em tela/conferencia, nunca somado
  em rubrica nomeada silenciosamente.
- Split juros x multa da mora de liquidacao usa percentuais do
  ProcedimentoDeCobranca como PARAMETRO; o total e sempre o caixa
  (ValorDoPagamento - ValorLiquido), nunca o teorico.

Consumidores: /controladoria/receitas (acruo), ROA-caixa, BI, tools de
agente. Silver-only (CLAUDE.md 13.2.1).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
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


class ReceitaOperacional(Auditable, Base):
    """Um evento de receita operacional liquidado (caixa) ou retido na fonte."""

    __tablename__ = "wh_receita_operacional"
    __table_args__ = (
        # Idempotencia do upsert: source_id sintetico montado pelo ETL com
        # (stream_key, fonte, id-origem, natureza) -- mesma estrategia do
        # uq_wh_dre_mensal_source.
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_receita_operacional_source"
        ),
        Index(
            "ix_wh_receita_operacional_tenant_comp",
            "tenant_id",
            "competencia",
        ),
        Index(
            "ix_wh_receita_operacional_tenant_stream_comp",
            "tenant_id",
            "stream_key",
            "competencia",
        ),
        Index(
            "ix_wh_receita_operacional_tenant_titulo",
            "tenant_id",
            "titulo_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Temporal: `data` = dia do evento de caixa (DataDaSituacao do titulo,
    # Data do lancamento, DataDeEfetivacao da recompra/operacao);
    # `competencia` = 1o dia do mes de `data` (agregacao mensal).
    data: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    competencia: Mapped[date] = mapped_column(Date, nullable=False)

    # Classificacao (denormalizada do catalogo na hora do ETL -- o fato e
    # reconstruivel, o catalogo e versionado). stream_key NULL = receita
    # detectada sem stream ativo = "nao classificado" (flag de governanca).
    stream_key: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    familia: Mapped[str | None] = mapped_column(String(30), nullable=True)
    natureza: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Regua contratual de referencia (ProcedimentoDeCobranca aplicado aos
    # dias de atraso) quando o VALOR cobrado foi NEGOCIADO (stream
    # mora_liquidacao_negociado, ENCARGO_NEGOCIADO) ou quando a fonte e
    # recompra (juros/multa lancados na negociacao). Desconto de mora
    # concedido = referencia - valor (linha com valor 0 e referencia > 0 =
    # mora perdoada por inteiro). NULL = nao se aplica.
    valor_referencia_regua: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )

    # Ancoras na fonte (ids nativos Bitfin; preenchidos conforme o grao do
    # stream -- titulo/operacao/recompra/lancamento).
    titulo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operacao_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recompra_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lancamento_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    documento: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Dimensoes de analise (ids nativos Bitfin, como em wh_dre_mensal).
    unidade_administrativa_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    produto_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cedente_entidade_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    cedente_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cedente_documento: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sacado_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sacado_documento: Mapped[str | None] = mapped_column(String(20), nullable=True)
