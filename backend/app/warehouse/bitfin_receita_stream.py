"""wh_bitfin_receita_stream -- catalogo de STREAMS de receita operacional (dim).

Cada stream = uma rota de caixa pela qual receita operacional entra,
ancorada nas tabelas NATIVAS do Bitfin que refletem liquidacao financeira
real (decisao 2026-06-10: a DemonstrativoDeResultado RECALCULA mora
teoricamente e ficou FORA da apuracao -- ver bitfin_adapter v2.5.0).

Fontes caixa-fieis por familia:

    mora_liquidacao   -> Titulo.ValorDoPagamento - ValorLiquido (>0)
                         (split juros x multa via percentuais do
                         ProcedimentoDeCobranca -- PARAMETRO, nunca valor)
    mora_prorrogacao  -> ContaCorrenteLancamento cod 028 (juros) / 151 (multa)
    mora_cartorio     -> ContaCorrenteLancamento cod 024 / 025
    mora_recompra     -> RecompraResultado (Efetivada=1) Juros/Multa/Desagio
    operacao          -> OperacaoRentabilidade (desagio + tarifas retidas
                         do liquido na efetivacao = caixa por construcao)
    tarifa_servico    -> ContaCorrenteLancamento (codigos de tarifa)
    repasse_custo     -> ContaCorrenteLancamento 003/015/053/088
    financeira        -> ContaCorrenteLancamento 031 SOMENTE com
                         Descricao='Correção Diária' (GOTCHA: 031 e bipolar --
                         'Rentabilidade de Debênture' e REPASSE a debenturista,
                         nunca receita)

`criterio` (JSONB) parametriza o ETL: codigos da conta grafica, filtros de
descricao, flags. O ETL le o catalogo e materializa `wh_receita_operacional`
(fato). Lancamento em codigo de receita SEM stream ativo -> fato com
stream_key NULL = "nao classificado" (flag de governanca, nunca chutado).

Versionamento espelha o padrao de regra do projeto (cascata + soft-delete,
CLAUDE.md 14.3): tenant_id NULL = global; override por tenant; ativa quando
valid_until IS NULL. Seed na migration b3f7a2c9e4d1.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Vocabulario fechado de naturezas (1 stream = 1 natureza; quando a mesma
# fonte produz 2 naturezas -- ex.: split juros x multa da mora de
# liquidacao -- sao 2 streams com o mesmo criterio de fonte).
NATUREZA_DESAGIO = "DESAGIO"
NATUREZA_JUROS_MORA = "JUROS_MORA"
NATUREZA_MULTA_MORA = "MULTA_MORA"
NATUREZA_TARIFA = "TARIFA"
NATUREZA_REPASSE_CUSTO = "REPASSE_CUSTO"
NATUREZA_FINANCEIRA = "FINANCEIRA"
NATUREZA_AD_VALOREM = "AD_VALOREM"

NATUREZAS_VALIDAS = frozenset(
    {
        NATUREZA_DESAGIO,
        NATUREZA_JUROS_MORA,
        NATUREZA_MULTA_MORA,
        NATUREZA_TARIFA,
        NATUREZA_REPASSE_CUSTO,
        NATUREZA_FINANCEIRA,
        NATUREZA_AD_VALOREM,
    }
)


class WhBitfinReceitaStream(Base):
    """Um stream de receita operacional (rota de caixa). Global ou override."""

    __tablename__ = "wh_bitfin_receita_stream"
    __table_args__ = (
        Index(
            "uq_wh_bitfin_receita_stream_active",
            "tenant_id",
            "stream_key",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where="valid_until IS NULL",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # NULL = stream global (vale para todos os tenants Bitfin); preenchido =
    # override do tenant (mesma stream_key vence a global).
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Identidade do stream (estavel; o fato referencia por esta chave).
    stream_key: Mapped[str] = mapped_column(String(50), nullable=False)
    familia: Mapped[str] = mapped_column(String(30), nullable=False)
    natureza: Mapped[str] = mapped_column(String(20), nullable=False)

    # Fonte Bitfin + criterio de extracao (parametriza o ETL):
    #   fonte_tabela: 'Titulo' | 'ContaCorrenteLancamento' |
    #                 'RecompraResultado' | 'OperacaoRentabilidade'
    #   criterio: {"codigos": ["028"], "descricao_eq": "...",
    #              "descricao_in": [...], "descricao_not_in": [...], ...}
    fonte_tabela: Mapped[str] = mapped_column(String(50), nullable=False)
    criterio: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Grao do fato gerado: 'titulo' | 'operacao' | 'recompra' | 'lancamento'.
    grao: Mapped[str] = mapped_column(String(20), nullable=False)

    # Receita retida do liquido na efetivacao (desagio, tarifas de operacao):
    # caixa por construcao, sem transito posterior em conta.
    retido_na_fonte: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
