"""Schemas do BI -> Panorama (Observatorio FIDC, mercado CVM).

Pagina `/bi/panorama` — analise ampla do segmento FIDC a partir do Informe
Mensal CVM (schema federado `cvm_remote.*`). Dado publico, sem tenant.

Fase 1: aba Visao Geral (KPIs macro + evolucao do PL + split por condominio
+ distribuicao de tamanho). Demais abas (Players, Risco & Liquidez, Lastro &
Prazo, Concentracao) ganham schemas proprios em iteracoes seguintes.
"""

from pydantic import BaseModel, Field


class PanoramaFilters(BaseModel):
    """Filtros globais da pagina Panorama (URL-persisted no frontend).

    Todos opcionais. `None` = filtro nao aplicado. Aplicados a 100% dos
    agregados via `_filter_where` no service (§7.2). Apenas campos
    ESTRUTURADOS da CVM — sem heuristica de nome. Padronizado x NP e situacao
    cadastral ficam de fora ate o ETL de `cad_fi_classe_fidc` (gated, Fase 2).
    """

    competencia: str | None = Field(default=None, description="'YYYY-MM'. None => ultima disponivel")
    condom: str | None = Field(default=None, description="'aberto' | 'fechado' (campo cvm condom)")
    faixa_pl: str | None = Field(
        default=None,
        description="Faixa de porte: 'lt50'|'50_200'|'200_500'|'500_1000'|'gt1000'",
    )
    tipo_carteira: str | None = Field(
        default=None, description="'propria' | 'cotas' (razao cotas-de-fundos / ativo)"
    )
    admin_cnpj: str | None = Field(default=None, description="CNPJ do administrador (cvm cnpj_admin)")


class PanoramaKpis(BaseModel):
    """KPIs macro do segmento (sob os filtros ativos)."""

    pl_total: float = Field(description="Soma do PL (R$)")
    n_fidc: int = Field(description="Quantidade de entidades reportantes")
    pl_medio: float = Field(description="PL medio por fundo (R$)")
    delta_fundos: int = Field(description="Variacao liquida de fundos vs competencia anterior")
    liquidez_pct: float = Field(description="Indice de liquidez ampla / PL (ponderado, %)")


class PlPonto(BaseModel):
    """Ponto da serie de evolucao do PL."""

    competencia: str  # 'YYYY-MM'
    pl: float
    n_fidc: int


class CondominioItem(BaseModel):
    """Split de PL por tipo de condominio (Aberto/Fechado)."""

    condom: str  # 'Aberto' | 'Fechado'
    n_fidc: int
    pl: float
    pct_pl: float


class TamanhoBucket(BaseModel):
    """Bucket da distribuicao de tamanho (faixa de PL)."""

    faixa: str  # rotulo legivel (ex.: '< R$ 50 mi')
    n_fidc: int
    pl: float


class CompletudeInfo(BaseModel):
    """Completude da publicacao da competencia mais recente.

    A CVM publica o Informe Mensal de FIDC de forma INCREMENTAL: os fundos
    entregam ao longo de semanas apos o fechamento do mes. A competencia
    corrente fica parcial por ~30-45 dias, fazendo o PL agregado parecer
    "cair" — quando na verdade so faltam fundos reportar. Este bloco sinaliza
    isso ao usuario (badge "preliminar") para nao confundir com queda real.

    Metrica GLOBAL (sem filtros): e propriedade da competencia, nao do recorte.
    """

    n_reportado: int = Field(description="Fundos (PL>0) na competencia alvo")
    n_referencia: int = Field(description="Fundos (PL>0) na competencia anterior (baseline)")
    pct_reportado: float = Field(description="100 * n_reportado / n_referencia")
    preliminar: bool = Field(description="True se pct_reportado < limiar (competencia parcial)")


class VisaoGeralData(BaseModel):
    """Payload da aba Visao Geral."""

    competencia: str  # 'YYYY-MM' resolvida
    kpis: PanoramaKpis
    completude: CompletudeInfo
    evolucao_pl: list[PlPonto]
    por_condominio: list[CondominioItem]
    distribuicao_tamanho: list[TamanhoBucket]


# ── Aba Players (administradoras) ───────────────────────────────────────────


class AdminRankingItem(BaseModel):
    """Linha do ranking de administradoras."""

    cnpj_admin: str
    admin: str
    qtd: int
    pct_qtd: float
    pl: float
    pct_pl: float
    pl_medio: float
    pl_mediano: float
    liquidez_pct: float


class PlayersData(BaseModel):
    """Payload da aba Players."""

    competencia: str
    total_fidc: int
    pl_total: float
    ranking: list[AdminRankingItem]  # top-N por PL


# ── Aba Lastro & Prazo ──────────────────────────────────────────────────────


class PrazoFaixa(BaseModel):
    """Faixa de prazo de vencimento da carteira a vencer."""

    faixa: str  # 'ate 30d', '31-60d', ...
    valor: float
    pct: float


class LastroPrazoData(BaseModel):
    """Payload da aba Lastro & Prazo.

    Decisao metodologica: distribuicao por faixa, NUNCA prazo medio em dias
    (a faixa +1080d e aberta/censurada — media seria artefato). Ver conversa
    2026-06-01.
    """

    competencia: str
    total_a_vencer: float
    distribuicao_prazo: list[PrazoFaixa]


# ── Aba Risco & Liquidez ────────────────────────────────────────────────────


class LiquidezCell(BaseModel):
    """Celula da matriz porte x condominio do indice de liquidez."""

    porte: str  # rotulo de faixa de PL
    condom: str  # 'Aberto' | 'Fechado'
    indice_ponderado: float  # % (liquidez ponderada / PL)
    mediana: float  # % (fundo mediano)
    n_fidc: int


class LiquidezSeriePonto(BaseModel):
    """Ponto da serie do indice de liquidez (ponderado vs mediano)."""

    competencia: str
    indice_ponderado: float
    mediana: float


class RiscoLiquidezData(BaseModel):
    """Payload da aba Risco & Liquidez."""

    competencia: str
    matriz: list[LiquidezCell]
    serie: list[LiquidezSeriePonto]


# ── Aba REALINVEST vs Mercado (cockpit comparativo) ─────────────────────────


class FundoMetricaComparada(BaseModel):
    """Uma metrica do fundo + posicionamento vs mercado/pares."""

    label: str
    valor: float
    unidade: str  # 'BRL' | '%' | 'dias'
    mercado_mediana: float | None = None  # mediana do mercado (mesma unidade)
    percentil_mercado: float | None = None  # 0-100 (posicao do fundo no mercado)
    percentil_pares: float | None = None  # 0-100 (vs pares: mesmo condominio + porte)


class FundoComparativoData(BaseModel):
    """Payload da aba REALINVEST vs Mercado (tear-sheet + percentis)."""

    competencia: str
    cnpj: str
    nome: str
    condom: str | None
    admin: str | None
    pl: float
    evolucao_pl: list[PlPonto]  # serie do proprio fundo
    metricas: list[FundoMetricaComparada]
    encontrado: bool  # False se o CNPJ nao reporta na competencia
