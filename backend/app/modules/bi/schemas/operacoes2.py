"""Schemas da L2 Operacoes2 (refatoracao 2026-05-03).

A pagina gira em torno de 5 indicadores-chave (VOP, Taxa, Prazo, Produto Top,
Receita Contratada) expostos num KPI Strip global, e 4 abas que sao lentes de
aprofundamento:

- Aba 1: Volume & Ritmo
- Aba 2: Produtos & Pricing
- Aba 3: Receita                 (futuro)
- Aba 4: Cedentes & Concentracao (futuro — depende de cedente_id em wh_operacao)

Cada endpoint retorna `BIResponse[<data>]` com proveniencia.

Decisao de design (2026-05-03):
- 1 delta por KPI, label "MoM" forcado (vs periodo imediatamente anterior de
  mesmo tamanho — o backend reutiliza `_shift_period_back`).
- Sparklines sao SEMPRE 12M corridos terminando em `periodo_fim` (ou hoje).
- Campos que dependem de `wh_dim_dia_util` (ritmo do mes, pace diario)
  retornam `None` quando a tabela esta vazia (degraded mode). Frontend
  renderiza placeholder.
"""

from pydantic import BaseModel, Field

from app.modules.bi.schemas.common import Point

# ─── KPI Strip ──────────────────────────────────────────────────────────────


class KpiCellNumeric(BaseModel):
    """Celula generica do strip (VOP, Taxa, Prazo, Receita).

    Strip dual (Opcao 4 paradigma 2026-05-03): cada cell carrega valor do
    PERIODO + valor do MES CORRENTE em paralelo. Frontend renderiza ambos.
    Sparkline e sempre 12M.

    Dois deltas distintos:
    - `delta_pct`: periodo atual vs periodo imediatamente anterior de mesmo
      tamanho (P/P, Period-over-Period). Tooltip em `comparacao_label_pt`.
    - `mes_corrente_delta_pct`: MTD same-period — primeiros N dias do mes
      corrente vs primeiros N dias do mes anterior (apples-to-apples).
      N = dia atual; clampa quando dia > ultimo dia do mes anterior.
      Frontend canonico exibe este como "↑ X% MTD" abaixo do mes_corrente_valor.
    """

    valor: float
    unidade: str = Field(description="'BRL' | '%' | 'dias'")
    delta_pct: float | None
    sparkline_12m: list[Point]
    # Mes corrente — agregado limitado a [1o dia mes do periodo_fim, periodo_fim].
    mes_corrente_valor: float
    mes_corrente_label: str = Field(description="Ex.: 'Maio/2026'")
    mes_corrente_delta_pct: float | None = Field(
        default=None,
        description=(
            "MTD same-period: mes corrente (1-N) vs mes anterior (1-N). "
            "N = dia atual do mes corrente, clampado ao ultimo dia do "
            "mes anterior em meses curtos."
        ),
    )


class KpiCellProduto(BaseModel):
    """Celula especifica do KPI #4 (Produto Top).

    `share_pct` em escala 0-100. `sparkline_share_12m` mostra a evolucao do
    share_pct mes a mes (12M).

    Strip dual: produto top do MES pode ser diferente do produto top do
    PERIODO (Faturizacao dominou 12M, mas DM virou lider em maio). Frontend
    pode mostrar ambos lado a lado.

    Dois deltas distintos (em pontos percentuais):
    - `delta_share_pp`: share do produto-top-do-periodo neste periodo vs no
      periodo imediatamente anterior de mesmo tamanho.
    - `mes_corrente_delta_share_pp`: MTD same-period — share do
      produto-top-DO-MES nos primeiros N dias do mes corrente vs share do
      MESMO produto nos primeiros N dias do mes anterior. Frontend canonico
      exibe este abaixo do mes_corrente_share_pct.
    """

    sigla: str
    nome: str | None
    share_pct: float
    delta_share_pp: float | None
    sparkline_share_12m: list[Point]
    # Mes corrente (pode ser produto diferente do top do periodo).
    mes_corrente_sigla: str
    mes_corrente_nome: str | None
    mes_corrente_share_pct: float
    mes_corrente_label: str
    mes_corrente_delta_share_pp: float | None = Field(
        default=None,
        description=(
            "MTD same-period: pp de variacao do share do produto-top-do-mes "
            "entre o MTD corrente e o MTD do mes anterior."
        ),
    )


class OperacoesKpiStripData(BaseModel):
    """Bundle dos 5 KPIs + label de comparacao."""

    vop: KpiCellNumeric
    taxa_media: KpiCellNumeric
    prazo_medio: KpiCellNumeric
    produto_top: KpiCellProduto
    receita_contratada: KpiCellNumeric
    # Tooltip do delta — descreve o range concreto comparado.
    # Ex.: "vs mar/26", "vs mai/24 a abr/25", "sem base de comparacao".
    comparacao_label_pt: str


# ─── Aba 1: Volume & Ritmo ──────────────────────────────────────────────────


class EvolucaoMensalPonto(BaseModel):
    """Ponto da evolucao 12M com contexto rico.

    `mm_3m` e a media movel de 3 meses (so populada do 3o mes em diante na
    serie). Frontend usa para a linha sobreposta no chart combo.
    """

    periodo: str = Field(description="ISO date 'YYYY-MM-DD' (1o dia do mes)")
    vop: float
    n_operacoes: int
    ticket_medio: float
    mm_3m: float | None


class MesDestaque(BaseModel):
    """Mes de melhor / pior VOP no periodo do filtro (mini-stats no rodape)."""

    periodo: str
    vop: float


class RitmoMesCorrente(BaseModel):
    """Linha 2 Card grande — VOP ate hoje vs mesmo nº DUs do mes anterior.

    DEPENDE de `wh_dim_dia_util` populada. Quando vazia, endpoint retorna
    `null` no campo `ritmo` da resposta.
    """

    vop_acumulado: float
    du_corridos: int
    du_total_mes: int
    vop_anterior_mesmo_du: float
    delta_pct: float | None = Field(
        description="VOP corrente vs VOP anterior no mesmo nº DUs"
    )
    projecao_fim_mes: float
    # Acumulado dia-a-dia para o mini chart de linha (corrente vs anterior).
    # `du_index` 1..N — eixo X categorico no frontend.
    acumulado_dia_a_dia: list["AcumuladoDiarioPonto"]
    # Quebra por UA: cada item carrega VOP MTD da UA + delta same-period DU
    # vs mes anterior. Usado para listagem textual no rodape do card Hero
    # do Ritmo. Ordenado por vop_corrente DESC (UA com maior VOP no mes
    # corrente vem primeiro). Vazio quando nao ha UA no resultado filtrado.
    ritmo_por_ua: list["RitmoUaItem"] = Field(default_factory=list)


class AcumuladoDiarioPonto(BaseModel):
    du_index: int
    corrente: float
    anterior: float


class RitmoUaItem(BaseModel):
    """Quebra por UA do ritmo do mes corrente — apenas dados textuais."""

    ua_id: int
    ua_nome: str
    vop_corrente: float = Field(description="VOP MTD da UA no mes corrente")
    delta_pct: float | None = Field(
        description=(
            "VOP MTD corrente vs VOP MTD do mes anterior no mesmo nº DUs. "
            "None quando nao ha base de comparacao (UA sem dados no mes "
            "anterior MTD)."
        )
    )


class PaceDiario(BaseModel):
    """Linha 2 Card sidekick — VOP medio por DU corrente vs mes anterior.

    DEPENDE de `wh_dim_dia_util`. `null` em degraded mode.
    """

    vop_du_corrente: float
    vop_du_anterior: float
    delta_pct: float | None


class KpiSecundario(BaseModel):
    """KPI escalar com delta MoM + sparkline 12M fechados.

    `sparkline_12m` traz a evolucao do indicador mes a mes nos ultimos 12
    meses fechados (M-12 a M-1, exclui o mes corrente parcial). Como cada
    KPI tem unidade/escala propria (count, BRL, BRL/titulo, BRL/DU), o slope
    deve ser interpretado em modo relativo (% sobre a media da propria
    serie) — analogo ao card "VOP por UA" mode="absolute".
    """

    valor: float
    delta_pct: float | None
    sparkline_12m: list[Point] = Field(default_factory=list)


class KpisSecundariosVolume(BaseModel):
    n_operacoes: KpiSecundario
    ticket_op: KpiSecundario
    ticket_titulo: KpiSecundario
    # `vop_du_medio` e null quando wh_dim_dia_util esta vazia.
    vop_du_medio: KpiSecundario | None


class QuebraDimensaoLinha(BaseModel):
    """Linha de barra horizontal por dimensao (UA, Produto).

    Strip dual: cada linha carrega vop+pct do PERIODO e vop+pct do
    MES CORRENTE. Frontend usa toggle "Periodo | Mes | Ambos" para alternar
    a renderizacao.

    Duas sparklines 12M sao expostas, escolhidas pelo frontend conforme a
    natureza da dimensao:

    - `sparkline_share_12m`: % do total mensal — usado em dimensoes onde a
      analise de DRIFT DE MIX importa (ex.: Produto, onde o mix de DM vs
      Faturizacao tem leitura de risco). Sob crescimento agregado, todas
      as categorias crescem em valor — share expoe ganho/perda relativo.

    - `sparkline_vop_12m`: VOP absoluto da categoria mes a mes — usado em
      dimensoes onde cada item tem TRAJETORIA propria (ex.: UA, onde
      RealInvest cresce com o mercado de capitais e A7 fica estavel
      como securitizadora). Aqui a leitura correta e "essa UA esta
      fazendo mais/menos que ela mesma no passado", nao share. Slope
      neste caso deve ser interpretado RELATIVO a media da propria
      serie (% por mes), nao em unidades absolutas — escala varia muito
      entre categorias.
    """

    categoria_id: str
    categoria: str
    # Periodo (filtro completo)
    vop: float
    pct: float = Field(description="% do total no periodo")
    delta_mom_pct: float | None
    delta_yoy_pct: float | None
    # Mes corrente
    vop_mes_corrente: float
    pct_mes_corrente: float = Field(description="% do total no mes corrente")
    # Sparkline 12M de share% (cada Point.valor em escala 0-100).
    sparkline_share_12m: list[Point] = Field(default_factory=list)
    # Sparkline 12M de VOP absoluto da categoria (Point.valor em BRL).
    sparkline_vop_12m: list[Point] = Field(default_factory=list)


class EvolucaoPorUaPonto(BaseModel):
    """Ponto da serie 12M segmentado por UA.

    Usado pelo Hero (Linha 1) com seletor de UA local — frontend filtra
    client-side a partir desta serie ja segmentada para mostrar a evolucao
    de uma UA especifica sem nova ida ao backend.
    """

    periodo: str = Field(description="ISO 'YYYY-MM-DD' (1o dia do mes)")
    ua_id: int
    ua_nome: str
    vop: float


class AbaVolumeRitmoData(BaseModel):
    """Bundle completo da Aba 1 — Volume & Ritmo."""

    # Linha 1
    evolucao_12m: list[EvolucaoMensalPonto]
    evolucao_12m_por_ua: list[EvolucaoPorUaPonto]
    melhor_mes: MesDestaque | None
    pior_mes: MesDestaque | None

    # Linha 2 (degraded quando DU vazio)
    ritmo: RitmoMesCorrente | None
    pace_diario: PaceDiario | None

    # Linha 3
    kpis_secundarios: KpisSecundariosVolume

    # Linha 4 — quebras (UA na L1, Produto na L4)
    por_ua: list[QuebraDimensaoLinha]
    por_produto: list[QuebraDimensaoLinha]


# Resolve forward ref de RitmoMesCorrente.acumulado_dia_a_dia
RitmoMesCorrente.model_rebuild()


# ─── Aba 2: Produtos & Pricing ──────────────────────────────────────────────


class MixTemporalProdutoPonto(BaseModel):
    """Ponto da serie 12M segmentada por produto (stacked bar do Hero L1).

    Janela e SEMPRE 12M FECHADOS (M-12 a M-1, exclui mes corrente parcial)
    via `_sparkline_12m_closed_window` — evita distorcao no inicio do mes.
    O mes corrente vai como destaque/marker no chart, nao como ponto na serie.
    """

    periodo: str = Field(description="ISO 'YYYY-MM-DD' (1o dia do mes)")
    produto_sigla: str
    vop: float
    n_operacoes: int
    taxa_media: float = Field(description="Ponderada por VOP (% a.m.)")
    prazo_medio: float = Field(description="Ponderado por VOP (dias)")


class RankingProdutoLinha(BaseModel):
    """Linha do ranking de produtos (DataTable da L2 Card A).

    Strip dual: cada linha carrega valores do PERIODO + 2 colunas de mes
    corrente (VOP + Taxa) na MESMA linha, sem expand/sub-row.

    Taxa, prazo e spread sao MEDIAS PONDERADAS por VOP:
      SUM(metric * total_bruto) / NULLIF(SUM(total_bruto), 0)
    """

    sigla: str
    nome: str | None
    # Periodo
    vop: float
    pct: float = Field(description="% do total no periodo (0-100)")
    delta_mom_pp: float | None = Field(
        description=(
            "Variacao de share em pp: share atual vs share no periodo "
            "imediatamente anterior de mesmo tamanho. None quando nao ha base."
        )
    )
    taxa_media: float = Field(description="% a.m., ponderada por VOP")
    prazo_medio: float = Field(description="dias, ponderado por VOP")
    spread_medio: float = Field(description="pp, ponderado por VOP")
    n_operacoes: int
    # Mes corrente (MTD same-period, apples-to-apples)
    vop_mes_corrente: float
    taxa_media_mes_corrente: float


class ScatterProdutoPonto(BaseModel):
    """Ponto agregado por produto no scatter Taxa x Prazo (L2 Card B).

    Sempre carrega 2 estados (periodo + mes corrente). Frontend renderiza
    ponto solido (periodo) + halo discreto (mes corrente) na mesma cor —
    sem toggle, paradigma "ambos visiveis sempre" da Aba 1.
    """

    sigla: str
    nome: str | None
    # Periodo
    prazo_medio: float
    taxa_media: float
    vop: float
    # Mes corrente
    prazo_medio_mes_corrente: float
    taxa_media_mes_corrente: float
    vop_mes_corrente: float


class HistogramaProdutoBucket(BaseModel):
    """Bucket de histograma quebrado por produto.

    Backend retorna buckets por produto para que o frontend possa filtrar
    client-side via chip multi-select sem nova ida ao servidor.
    """

    produto_sigla: str
    bucket_label: str = Field(description="Ex.: '0-30 d', '1.5-2.0%'")
    bucket_lower: float = Field(description="Limite inferior (numerico, p/ ordenacao)")
    bucket_upper: float = Field(description="Limite superior (exclusivo)")
    count: int
    vop: float


class HistogramaTaxasResumo(BaseModel):
    """Histograma de taxas + estatisticas ponderadas.

    `bucket_size_pp` e dinamico: 0.25 pp quando range observado <= 5 pp,
    0.5 pp quando > 5 pp; clampa em ~30 buckets max.
    """

    buckets: list[HistogramaProdutoBucket]
    media_ponderada: float = Field(description="% a.m., Σ(taxa * vop) / Σ vop")
    mediana: float = Field(description="% a.m., mediana ponderada por VOP")
    bucket_size_pp: float


class HistogramaPrazosResumo(BaseModel):
    """Histograma de prazos com buckets fixos: 0-30, 31-60, 61-90, 91-180, 180+."""

    buckets: list[HistogramaProdutoBucket]


class ProdutoDestaque(BaseModel):
    """Mini-stat do rodape do Hero L1 (lider, maior alta, maior queda)."""

    sigla: str
    nome: str | None
    valor: float = Field(
        description="Share % (lider) ou Δ pp de share (maior alta/queda)"
    )


class AbaProdutosPricingData(BaseModel):
    """Bundle completo da Aba 2 — Produtos & Pricing."""

    # Linha 1 — Hero
    mix_temporal_12m: list[MixTemporalProdutoPonto]
    lider_periodo: ProdutoDestaque | None
    maior_alta_mom: ProdutoDestaque | None
    maior_queda_mom: ProdutoDestaque | None

    # Linha 2 — Ranking + Scatter agregado
    ranking: list[RankingProdutoLinha]
    scatter_produtos: list[ScatterProdutoPonto]

    # Linha 3 — Histogramas
    histograma_taxas: HistogramaTaxasResumo
    histograma_prazos: HistogramaPrazosResumo
