"""Schemas da L2 Operacoes.

L3 tabs: Volume | Taxa | Prazo | Ticket | Receita contratada | Dia util

Cada endpoint retorna `BIResponse[<data>]` com proveniencia.
"""

from pydantic import BaseModel, Field

from app.modules.bi.schemas.common import KPI, CategoryValue, Point


class OperacoesResumo(BaseModel):
    """KPIs principais da L2 Operacoes para o periodo filtrado."""

    total_operacoes: KPI
    volume_bruto: KPI
    ticket_medio: KPI
    taxa_media: KPI
    prazo_medio: KPI
    receita_contratada: KPI
    # Narrativa "o que aconteceu" — 1-2 frases factuais sobre o periodo.
    # `None` quando nao ha dado suficiente para narrar (periodo vazio).
    takeaway_pt: str | None = None


#
# L3 Volume — tipos auxiliares
#


class PointDim(BaseModel):
    """Ponto temporal segmentado por uma dimensao adicional.

    Usado em series empilhadas (ex.: volume por produto no tempo, volume
    por UA no tempo). `categoria_id` e a chave estavel (sigla do produto,
    UA id) para amarrar com filtros; `categoria` e o label amigavel exibido
    no chart.
    """

    periodo: str = Field(description="Data ISO 'YYYY-MM-DD' (primeiro dia do mes)")
    categoria_id: str = Field(description="ID estavel (sigla de produto, id de UA)")
    categoria: str = Field(description="Label amigavel para exibicao")
    valor: float


class CategoryValueDelta(BaseModel):
    """Agregacao por categoria + delta vs periodo imediatamente anterior.

    Campos opcionais `taxa_media_pct`, `prazo_medio_dias`, `tendencia_90d`
    e `tendencia_90d_delta_pct` sao preenchidos apenas quando o backend
    tem contexto para isso (hoje: `por_produto` no L3 Volume). Outras
    decomposicoes (UA, cedente) os deixam em `None` / vazio.
    """

    categoria: str
    categoria_id: str | None = None
    valor: float
    quantidade: int | None = None
    delta_pct: float | None = Field(
        default=None,
        description="Variacao % vs periodo anterior (mesmo tamanho, deslocado). None quando sem base.",
    )

    # Detalhamento analitico (opcional, populado por L3 Volume > por_produto)
    taxa_media_pct: float | None = Field(
        default=None,
        description="Taxa media ponderada por volume (% a.m.) no periodo filtrado.",
    )
    prazo_medio_dias: float | None = Field(
        default=None,
        description="Prazo medio real ponderado por volume (em dias) no periodo filtrado.",
    )
    tendencia_90d: list[Point] = Field(
        default_factory=list,
        description="Serie semanal (13 pontos) de volume nos ultimos 90 dias \u2014 independente do filtro.",
    )
    tendencia_90d_delta_pct: float | None = Field(
        default=None,
        description="Variacao % do total dos ultimos 90d vs 90d anteriores.",
    )


class TopCedenteItem(BaseModel):
    """Cedente no ranking top-N por volume."""

    ranking: int
    cedente_id: int
    nome: str
    volume: float
    delta_pct: float | None = None


class VolumeResumoDeltas(BaseModel):
    """KPIs de contexto da aba Volume com deltas e sparklines 12M.

    Sparklines sao FIXAS em 12M corridos (terminando na data-fim do filtro),
    independentemente do tamanho do filtro de periodo — um sparkline de 3M
    seria visualmente inutil.

    Deltas (`*_delta_pct`): SEMPRE comparam o periodo do filtro contra o
    periodo imediatamente anterior de mesmo tamanho. Filtro = 1 mes vira MoM
    natural; filtro = 12 meses vira YoY natural; filtro = 90 dias vira
    "vs 90 dias anteriores". Eliminamos o par MoM+YoY na UI porque com
    filtro grande (ex.: 12 meses) eles tem semanticas diferentes do numero
    grande exibido (MoM = ultimo mes vs penultimo nao bate com soma de 12m).
    `comparacao_label_pt` carrega o range exato comparado (tooltip).

    `produto_lider_*`: produto com maior participacao no volume; delta_pp
    e a variacao em pontos percentuais da fatia de mercado interno.
    """

    # Volume
    volume_total: float
    volume_delta_pct: float | None
    volume_sparkline_12m: list[Point]

    # Ticket medio por OPERACAO (volume_total / n_operacoes)
    ticket_medio: float
    ticket_delta_pct: float | None
    ticket_sparkline_12m: list[Point]

    # Ticket medio por TITULO (volume_total / soma_quantidade_de_titulos)
    # Metrica complementar: dentro de uma mesma operacao pode haver varios
    # titulos; esse KPI expressa o valor medio por titulo ("ticket real de
    # recebivel"). Util para entender pulverizacao vs concentracao.
    ticket_medio_titulo: float
    ticket_medio_titulo_delta_pct: float | None
    ticket_medio_titulo_sparkline_12m: list[Point]

    # Produto lider — sigla mantida como ID estavel (filtros, links);
    # `nome` exibido na UI ("Faturizacao" e mais informativo que "FAT").
    produto_lider_sigla: str
    produto_lider_nome: str | None
    produto_lider_pct: float
    produto_lider_delta_pp: float | None
    produto_lider_sparkline_12m: list[Point]

    # Tooltip — descreve o range concreto que `*_delta_pct` esta comparando.
    # Ex.: "vs mai/24 a abr/25" / "vs mes anterior" / "sem base de comparacao".
    comparacao_label_pt: str


class SeriesEVolume(BaseModel):
    """L3 Volume — serie configuravel + cortes + top-N + contexto.

    Responde a 8 perguntas-chave do diretor:
      1. Estou crescendo? → `resumo` (MoM, YoY, sparkline)
      2. De onde vem o crescimento? → `evolucao_por_produto`, `evolucao_por_ua`
      3. Quem sao meus maiores clientes? → `top_cedentes`
      4. Estou concentrado? → `resumo.concentracao_top10_pct`
      5. Cresco por preco ou por mix? → `evolucao_taxa/prazo/ticket` (overlay)
      6. Cliente novo ou recorrente? → (Onda 2)
      7. Tem sazonalidade? → `evolucao_yoy` (Onda 2)
      8. Drill-down → frontend via cross-filter (existente)
    """

    # Chart principal — 3 visoes alternativas (toggle no frontend).
    evolucao: list[Point]
    evolucao_por_produto: list[PointDim]
    evolucao_por_ua: list[PointDim]

    # Decomposicao.
    por_produto: list[CategoryValueDelta]
    por_ua: list[CategoryValueDelta]
    top_cedentes: list[TopCedenteItem]

    # Contexto (KPIs de topo).
    resumo: VolumeResumoDeltas

    # Overlays opcionais (chart principal exibe no eixo Y secundario).
    # Mesmos periodos que `evolucao` — serie pareada ponto a ponto.
    evolucao_taxa_media: list[Point]
    evolucao_prazo_medio: list[Point]
    evolucao_ticket_medio: list[Point]


class SeriesETaxa(BaseModel):
    """L3 Taxa — taxa de juros media ponderada (por volume)."""

    evolucao: list[Point]
    por_produto: list[CategoryValue]
    por_modalidade: list[CategoryValue]


class SeriesEPrazo(BaseModel):
    """L3 Prazo — prazo medio real ponderado (por volume)."""

    evolucao: list[Point]
    por_produto: list[CategoryValue]


class SeriesETicket(BaseModel):
    """L3 Ticket — ticket medio por operacao (bruto / numero de operacoes)."""

    evolucao: list[Point]
    por_produto: list[CategoryValue]
    por_cedente_top: list[CategoryValue]


class SeriesEReceita(BaseModel):
    """L3 Receita contratada — juros + tarifas contratadas na operacao."""

    evolucao: list[Point]
    por_componente: list[CategoryValue]
    por_produto: list[CategoryValue]


class SeriesEDiaUtil(BaseModel):
    """L3 Dia util — distribuicao de efetivacao por dia util do mes."""

    por_dia_util: list[Point]
    por_dia_semana: list[CategoryValue]
