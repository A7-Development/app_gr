"""Schemas da L2 Operacoes2 (refatoracao 2026-05-03).

VOP Potencial (2026-05-09):
- VOP Potencial = vop_realizado_mtd + caixa_disponivel + liquidacoes_previstas
- Apurado para o mes corrente, consolidado e por UA.
- Default: filtra UAs com `tipo IN (1, 2)` (FIDC + Securitizadora). Quando o
  usuario passa `ua_id` explicito, respeita a selecao (incluindo Onboard tipo
  NULL se quiser).
- Caixa: ultima snapshot por (UA, conta) com flags estruturais (`ativa=true`,
  `eh_escrow=false`, `eh_caucao=false`, `eh_travada=false`).
- Liquidacoes: titulos com `situacao=0`, `saldo_devedor>0`, `sustado=false`,
  `data_de_vencimento_efetiva` entre hoje e fim do mes.
- Filtro `produto_sigla` aplica-se APENAS a `vop_realizado_mtd` (caixa e
  liquidacoes nao tem dimensao produto canonica).

A pagina gira em torno de 5 indicadores-chave (VOP, Taxa, Prazo, Produto Top,
Receita Contratada) expostos num KPI Strip global, e 5 abas que sao lentes de
aprofundamento:

- Aba 0: Mes corrente            (default — variance decomposition por DU)
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

Decisao de design (2026-05-08, Aba 0 Mes corrente):
- Aba 0 responde "como esta indo o mes" via decomposicao de variancia em 6
  KPIs (VOP, Receita, Taxa, Prazo, Mix, Concentracao). Cada KPI tem tecnica
  adequada ao seu tipo:
    * Aditivos (VOP, Receita)   -> Variance bridge (drivers somam ao delta)
    * Medias ponderadas (Taxa, Prazo) -> PVM bridge (mix effect + intra effect)
    * Composicao (Mix)          -> Dumbbell (prior_share vs current_share)
    * Razao (Concentracao)      -> HHI delta + top movements de share
- Comparacao base: mesmo numero de DUs do mes anterior (paridade DU).
- Threshold de surfacing de drivers: ≥5%% do |delta_total| AND ≥R$ 500k abs.
  Drivers abaixo do threshold rolam pra "Outros".
- Projecao de fechamento: linear simples (current * du_totais / du_decorridos).
  So aplicada a aditivos (VOP, Receita).
- Dimensoes disponiveis: produto, ua, faixa_ticket. Cedente fica pra fase 2
  (depende de cedente_id em wh_operacao).
"""

from datetime import date
from typing import Literal

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


class VopDiarioPonto(BaseModel):
    """VOP por dia-calendario do mes corrente.

    Cobre TODOS os dias do mes (1..ultimo_dia), incluindo sabados, domingos
    e feriados. Para dias passados/hoje: `vop` = SUM(Operacao.total_bruto)
    daquele dia (0 quando nao houve operacao efetivada). Para dias futuros:
    `vop` = None — frontend renderiza barra ausente, mas o dia ainda aparece
    no eixo X (placeholder de prazo restante).

    `eh_dia_util` permite UI dimming/destaque de fim de semana e feriado.
    """

    data: date
    vop: float | None = Field(
        description="VOP do dia em BRL. None para dias futuros."
    )
    eh_dia_util: bool = Field(
        description="True quando o dia e util (dim_dia_util). False = sab/dom/feriado."
    )
    eh_futuro: bool = Field(description="True para dias > hoje (sem VOP apurado).")
    # Campos opt-in de operacoes4 (regime caixa). None quando service nao
    # enriqueceu o ponto (paginas /bi/operacoes3 etc continuam sem custo).
    receita: float | None = Field(
        default=None,
        description="Receita do dia (regime caixa: 4 buckets de wh_operacao).",
    )
    yield_pct: float | None = Field(
        default=None,
        description="receita / vop_bruto do dia em % a.m. None se vop=0.",
    )


class VopMtdPorUa(BaseModel):
    """Agregado MTD do VOP por UA (alimenta header KPI quando UA filtrada
    no card VOP Diario).

    Pra cada UA com operacao no mes corrente, carrega:
      - valor_mtd: VOP MTD da UA (1o dia do mes a hoje)
      - delta_vop_du_pct: VOP-DU (paridade DU vs mes anterior nos mesmos N DUs)
        — None quando nao ha base de comparacao.
    """

    ua_id: int
    ua_nome: str
    valor_mtd: float
    delta_vop_du_pct: float | None


class VopDiarioPorUaPonto(BaseModel):
    """VOP por (dia-calendario, UA) do mes corrente — alimenta o modo
    'Por UA' do card VOP Diario (stacked bar com cores por UA).

    Mesmas regras de `VopDiarioPonto` (todos os dias, sab/dom/feriado, dias
    futuros = None), porem com quebra por unidade administrativa. Frontend
    pivota num dict {ua_id -> serie[]} para montar stacked bar.
    """

    data: date
    ua_id: int
    ua_nome: str
    vop: float | None = Field(
        description="VOP do dia/UA em BRL. None para dias futuros."
    )
    eh_dia_util: bool
    eh_futuro: bool


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


# ─── Aba 0: Mes corrente (variance decomposition) ───────────────────────────
#
# Aba que responde "como esta indo o mes" via decomposicao do delta MTD vs
# mes anterior até mesmo numero de DUs. 6 cards com tecnicas diferentes:
#
#   - VOP / Receita         -> Variance bridge (aditivo)
#   - Taxa / Prazo          -> PVM bridge (mix effect + intra effect)
#   - Mix produtos          -> Dumbbell prior_share vs current_share
#   - Concentracao (HHI)    -> Delta HHI + top movements de share
#
# Threshold de surfacing de drivers: ≥5%% do |delta_total| AND ≥R$ 500k abs.
# Drivers abaixo rolam pra "Outros".


Dimension = Literal["produto", "ua", "faixa_ticket"]


class DriverContribution(BaseModel):
    """Contribuicao de um driver (membro de uma dimensao) ao delta de um KPI.

    Para metricas aditivas (VOP, Receita): `contribution_brl` SOMA ao delta.
    Para PVM (Taxa, Prazo): `contribution_brl` representa o efeito do membro
    em uma das duas componentes (mix ou intra) — ja na unidade do KPI (pp ou
    dias). O frontend rotula adequadamente.
    """

    member_id: str = Field(description="ID estavel da categoria (sigla, uuid str, label de bucket)")
    member_label: str = Field(description="Label amigavel exibido na barra do bridge")
    contribution_brl: float = Field(
        description=(
            "Contribuicao ao delta. Aditiva nas variance bridges (VOP/Receita) "
            "ou unidade do KPI (pp em Taxa, dias em Prazo) nas PVM bridges. "
            "Sinalizada: positivo puxa pra cima, negativo pra baixo."
        )
    )
    contribution_pct: float | None = Field(
        default=None,
        description=(
            "Percentual da contribuicao sobre o |delta total|. Util pro frontend "
            "ordenar/destacar drivers. None quando delta total = 0."
        ),
    )
    prior_value: float
    current_value: float


class VarianceBridgeData(BaseModel):
    """Decomposicao para metricas ADITIVAS (VOP, Receita).

    Bridge horizontal: prior_anchor → +driver1 → +driver2 → -driverN → current_anchor.
    Drivers sao ordenados por |contribution_brl| desc. Drivers abaixo do
    threshold (5%% do |delta_total| AND R$ 500k abs) rolam para `outros_rollup`.

    Anchor labels exemplo:
      prior_anchor_label   = "VOP abr/2026 ate DU 8"
      current_anchor_label = "VOP atual ate DU 8"
    """

    prior_anchor_label: str
    prior_anchor_value: float
    current_anchor_label: str
    current_anchor_value: float
    delta_brl: float = Field(description="current_anchor_value - prior_anchor_value")
    delta_pct: float | None = Field(
        description="(delta_brl / prior_anchor_value) * 100, None quando prior = 0"
    )
    drivers: list[DriverContribution] = Field(
        description="Drivers acima do threshold, ordenados por |contribution_brl| desc"
    )
    outros_rollup: DriverContribution | None = Field(
        default=None,
        description="Soma dos drivers abaixo do threshold. None quando todos estao acima.",
    )
    unidade: Literal["BRL"] = "BRL"


class ProjectionBridgeData(BaseModel):
    """Projecao linear de fechamento para metrica aditiva.

    Modelo: current_anchor_value * (du_totais_mes / du_decorridos), aplicado
    membro a membro. So faz sentido em metricas aditivas. Disponivel apenas
    quando wh_dim_dia_util esta populado.

    Bridge horizontal: current_anchor → +projecao_driver1 → ... → projected_close.
    Drivers extrapolados sao a parcela "ainda a vir" (projetado - current).
    """

    current_anchor_label: str
    current_anchor_value: float
    projected_close_label: str = Field(description="Ex.: 'Projecao mai/2026'")
    projected_close_value: float
    delta_brl: float = Field(description="projected_close - current (parcela faltante)")
    delta_pct: float | None
    drivers: list[DriverContribution] = Field(
        description="Drivers da parcela faltante, mesmas regras de threshold/rollup"
    )
    outros_rollup: DriverContribution | None = None
    unidade: Literal["BRL"] = "BRL"


class PvmBridgeData(BaseModel):
    """Decomposicao PVM para MEDIAS PONDERADAS (Taxa, Prazo).

    Bridge de 4 colunas: prior_avg → +mix_effect → +intra_effect → current_avg.

    Mix effect e intra effect somam exatamente ao delta total (Marshall-Edgeworth):

      mix_effect   = Σ (current_share_i - prior_share_i) * prior_avg_i
      intra_effect = Σ current_share_i * (current_avg_i - prior_avg_i)
      delta_total  = mix_effect + intra_effect

    Onde share_i e o share de volume da categoria i (somam 1.0 em cada periodo)
    e avg_i e o valor da metrica naquela categoria.

    Top contributors sao listados separadamente para cada efeito — `top_mix_*`
    contem os membros com maior contribuicao individual ao mix effect, idem
    para intra. Mesmas regras de threshold/rollup.
    """

    prior_anchor_label: str
    prior_anchor_value: float
    current_anchor_label: str
    current_anchor_value: float
    delta: float = Field(description="current - prior (na unidade do KPI)")
    delta_unidade: Literal["pp", "dias"]
    mix_effect: float = Field(description="Σ (current_share - prior_share) * prior_avg_i")
    intra_effect: float = Field(description="Σ current_share * (current_avg - prior_avg_i)")
    top_mix_contributors: list[DriverContribution] = Field(
        description="Top membros pelo |contribuicao| ao mix_effect"
    )
    top_intra_contributors: list[DriverContribution] = Field(
        description="Top membros pelo |contribuicao| ao intra_effect"
    )
    outros_mix_rollup: DriverContribution | None = None
    outros_intra_rollup: DriverContribution | None = None


class DumbbellPoint(BaseModel):
    """Um ponto do dumbbell (uma categoria com prior + current share)."""

    member_id: str
    member_label: str
    prior_share_pct: float = Field(description="0-100")
    current_share_pct: float = Field(description="0-100")
    delta_share_pp: float = Field(description="current - prior, em pontos percentuais")
    prior_value: float = Field(description="VOP absoluto da categoria no prior")
    current_value: float = Field(description="VOP absoluto da categoria no current")


class DumbbellSeriesData(BaseModel):
    """Mix de produtos: shift de share entre prior e current.

    Pontos ordenados por |delta_share_pp| desc, top 7 categorias retornadas.
    Categorias com share < 1%% em ambos os periodos sao filtradas out.
    """

    prior_anchor_label: str
    current_anchor_label: str
    points: list[DumbbellPoint]


class ConcentracaoMovement(BaseModel):
    """Categoria que ganhou ou perdeu share entre prior e current."""

    member_id: str
    member_label: str
    prior_share_pct: float
    current_share_pct: float
    delta_share_pp: float


class ConcentracaoDeltaData(BaseModel):
    """HHI (Herfindahl-Hirschman) + top movements de share.

    HHI normalizado em [0, 10000]: HHI = Σ (share_pct_i)² onde share_pct_i e
    o share da categoria i em escala 0-100 e a soma do quadrado vai de 0
    (perfeitamente diluido) a 10000 (monopolio).

    Calculado sobre a dimensao escolhida (default: produto). Top-3 share
    captura concentracao mais facil de ler ("os 3 maiores produtos sao X%%
    do volume").

    Movimentos: top 3 ganhadores de share + top 3 perdedores (separados pra
    leitura simetrica no card).
    """

    dimension_label: str = Field(description="Label legivel da dimensao avaliada")
    prior_anchor_label: str
    current_anchor_label: str
    hhi_prior: float = Field(description="HHI no periodo anterior (0-10000)")
    hhi_current: float = Field(description="HHI no periodo atual (0-10000)")
    delta_hhi: float = Field(description="hhi_current - hhi_prior")
    top_3_share_prior: float = Field(description="Share % dos top 3 do PERIODO ANTERIOR")
    top_3_share_current: float = Field(description="Share % dos top 3 do PERIODO ATUAL")
    delta_top_3_pp: float
    movements_gainers: list[ConcentracaoMovement] = Field(
        description="Top 3 ganhadores de share (sorted by delta_share_pp desc)"
    )
    movements_losers: list[ConcentracaoMovement] = Field(
        description="Top 3 perdedores de share (sorted by delta_share_pp asc)"
    )


class AbaMesCorrenteData(BaseModel):
    """Bundle da Aba 0 — Mes corrente (variance decomposition).

    Estrutura:
      - 1 narrative_sentence (template determinístico server-side)
      - 6 decomposicoes (uma por KPI), cada uma com tecnica adequada
      - Metadata de paridade DU (du_decorridos, du_totais_mes, comparacao_label_pt)
      - Dimensao ativa para variance/PVM (produto | ua | faixa_ticket)

    Quando wh_dim_dia_util esta vazia, a paridade DU degrada para paridade
    de dia corrido (`du_disponivel = false`). Projecoes ficam None nesse caso.
    """

    narrative_sentence: str = Field(
        description="Frase pt-BR multi-KPI gerada server-side (template deterministico)"
    )
    comparacao_label_pt: str = Field(
        description="Ex.: 'comparado a abr/2026 ate DU 8 (de 21)'"
    )
    du_decorridos: int = Field(
        description="Numero de DUs decorridos no mes corrente (ate periodo_fim/hoje)"
    )
    du_totais_mes: int = Field(description="Total de DUs do mes corrente (calendario ANBIMA)")
    du_disponivel: bool = Field(
        description="False quando wh_dim_dia_util esta vazia (degraded para dia corrido)"
    )

    # Decomposicoes
    vop: VarianceBridgeData
    vop_projecao: ProjectionBridgeData | None
    receita: VarianceBridgeData
    receita_projecao: ProjectionBridgeData | None
    taxa: PvmBridgeData
    prazo: PvmBridgeData
    mix: DumbbellSeriesData
    concentracao: ConcentracaoDeltaData

    # Serie diaria de VOP do mes corrente (todos os dias do calendario).
    # Alimenta o card "VOP Diario" — irmao visual do "Evolucao do VOP"
    # (granularidade mensal) usado na Aba 1 Volume & Ritmo.
    vop_diario: list[VopDiarioPonto] = Field(default_factory=list)

    # Dimensao ativa para a decomposicao das bridges (VOP, Receita, Taxa, Prazo)
    dimension_active: Dimension
    dimensions_disponiveis: list[Dimension] = Field(
        default_factory=lambda: ["produto", "ua", "faixa_ticket"]
    )


# ─── VOP Potencial ───────────────────────────────────────────────────────────


class VopPotencialPorUa(BaseModel):
    """Decomposicao por UA do VOP Potencial."""

    ua_id: int
    ua_nome: str
    ua_tipo: int | None = Field(
        description="Bitfin.UnidadeAdministrativa.Tipo: 1=FIDC, 2=Securitizadora, NULL=Outras"
    )
    vop_realizado_mtd: float = Field(description="VOP efetivado entre mes_inicio e hoje, em BRL")
    caixa_disponivel: float = Field(
        description="Saldo total das contas livres da UA (sem escrow/caucao/trava), em BRL"
    )
    liquidacoes_previstas: float = Field(
        description="Soma de saldo_devedor de titulos com vencimento entre hoje e mes_fim, em BRL"
    )
    vop_potencial: float = Field(description="vop_realizado_mtd + caixa + liquidacoes_previstas")


class VopPotencialData(BaseModel):
    """VOP Potencial -- consolidado e por UA.

    Janela temporal: mes corrente. `vop_realizado_mtd` cobre [mes_inicio, hoje];
    `liquidacoes_previstas` cobre (hoje, mes_fim]; `caixa_disponivel` e snapshot
    em `hoje` (ultima posicao conhecida por conta).

    Quando o filtro `ua_id` da pagina e None, default e `tipo IN (1, 2)`.
    """

    mes_inicio: date
    mes_fim: date
    hoje: date

    # Consolidado das UAs incluidas
    vop_realizado_mtd: float
    caixa_disponivel: float
    liquidacoes_previstas: float
    vop_potencial: float

    # Quebra por UA (sempre presente; lista vazia se nenhuma UA elegivel)
    por_ua: list[VopPotencialPorUa]


# ═══════════════════════════════════════════════════════════════════════════
# Aba "Mes Corrente v3" — pagina /bi/operacoes3
# ═══════════════════════════════════════════════════════════════════════════
#
# Reorienta a aba pro socio-diretor. Responde uma pergunta de cabeca:
#   "Como ta o mes? Onde estou ganhando, onde estou perdendo?"
#
# Estrutura final visual:
#   L1 Termometro: 5 KPIs (VOP, Receita, Taxa, Prazo, Potencial) — cada um
#      com valor + 2 deltas (VOP-DU paridade DU e MOM normalizado por DU).
#      Potencial e absoluto (sem delta).
#   L2 Hero VOP do mes: VOP Diario (col-span-2) + VOP Waterfall (col-span-1).
#      Drill por dia abre Sheet com operacoes do dia.
#   L3 Movimentos (Cedentes / Produtos / Taxas / Prazos)  -> PR2
#   L4 Sinais discretos                                    -> PR3
#   L5 Decomposicao avancada (collapsible, fechada default): Receita, Taxa,
#      Prazo, Mix, Concentracao — reusa schemas existentes.
#
# DESIGN NOTAS:
# - VOP-DU (paridade DU): MTD do mes corrente vs MTD do mes anterior nos
#   mesmos N DUs decorridos. Apples-to-apples temporal.
# - MOM normalizado por DU: pace_corrente vs pace_mes_anterior_fechado, onde
#   pace = valor / DUs do periodo. Pra valores absolutos (VOP, Receita).
#   Pra medias ponderadas (Taxa, Prazo), MOM = corrente vs mes_anterior_fechado
#   direto (media com media, nao normaliza por DU).


class MesCorrenteKpiCell(BaseModel):
    """Cell do termometro: 1 valor + 2 deltas (VOP-DU e MOM-norm-DU).

    `delta_vop_du_pct`: variacao percentual MTD corrente vs MTD do mes
    anterior no mesmo numero de DUs (paridade). None quando nao ha base
    de comparacao ou degraded mode (du_disponivel=false).

    `delta_mom_pct`: variacao percentual do RITMO (pace por DU) do mes
    corrente vs ritmo do mes anterior fechado. Para Taxa/Prazo (medias
    ponderadas), e comparacao direta sem normalizacao por DU. None quando
    nao ha base.

    `unidade`: "BRL" | "%" | "dias" — frontend formata adequadamente.
    """

    valor: float
    delta_vop_du_pct: float | None = Field(
        description="MTD vs MTD mes anterior nos mesmos N DUs (paridade)"
    )
    delta_mom_pct: float | None = Field(
        description="Ritmo (pace/DU) vs ritmo mes anterior fechado. Para "
        "Taxa/Prazo, comparacao direta sem normalizacao por DU."
    )
    unidade: str = Field(description="'BRL' | '%' | 'dias'")
    mes_label: str = Field(description="Ex.: 'mai/26' (mes corrente)")


class MesCorrentePotencialCell(BaseModel):
    """Cell Potencial — absoluto, sem delta.

    Reusa o calculo do VOP Potencial (vop_realizado_mtd + caixa + a liquidar).
    Frontend mostra apenas valor + sublabel descritivo das 3 parcelas.
    """

    valor: float = Field(description="VOP Potencial total em BRL")
    realizado: float = Field(description="VOP MTD efetivado")
    caixa: float = Field(description="Caixa disponivel nas UAs incluidas")
    a_liquidar: float = Field(description="Liquidacoes previstas ate fim do mes")
    mes_label: str


class MesCorrenteTermometro(BaseModel):
    """Termometro do mes corrente — 5 cells consolidados."""

    vop: MesCorrenteKpiCell
    receita: MesCorrenteKpiCell
    taxa: MesCorrenteKpiCell
    prazo: MesCorrenteKpiCell
    potencial: MesCorrentePotencialCell


class AbaMesCorrenteV3Data(BaseModel):
    """Bundle da aba /bi/operacoes3 — Mes Corrente v3 (socio-diretor view).

    Reutiliza schemas existentes para nao duplicar logica:
      - `vop_diario`: serie diaria do mes (alimenta hero L2 esquerda)
      - `vop`: variance bridge (alimenta hero L2 direita)
      - `receita`, `taxa`, `prazo`, `mix`, `concentracao`: decomposicao
        avancada (L5 collapsible, fechada default)

    Campos novos (especificos v3):
      - `termometro`: 5 KPIs com dupla comparacao (L1)
      - `du_decorridos`, `du_totais_mes`, `du_disponivel`: contexto
      - `comparacao_label_pt`: ex.: 'comparado a abr/2026 ate DU 12 (de 21)'
    """

    termometro: MesCorrenteTermometro
    comparacao_label_pt: str
    du_decorridos: int
    du_totais_mes: int
    du_disponivel: bool

    # Reuso: hero L2
    vop_diario: list[VopDiarioPonto] = Field(default_factory=list)
    # Quebra do VOP diario por UA — alimenta filtro de UA do hero L2.
    vop_diario_por_ua: list[VopDiarioPorUaPonto] = Field(default_factory=list)
    # Agregados MTD por UA (valor + VOP-DU) — alimenta header KPI quando
    # uma UA especifica e selecionada no card VOP Diario.
    vop_mtd_por_ua: list[VopMtdPorUa] = Field(default_factory=list)
    vop: VarianceBridgeData
    vop_projecao: ProjectionBridgeData | None

    # Reuso: L5 decomposicao avancada
    receita: VarianceBridgeData
    receita_projecao: ProjectionBridgeData | None
    taxa: PvmBridgeData
    prazo: PvmBridgeData
    mix: DumbbellSeriesData
    concentracao: ConcentracaoDeltaData


# ─── Drill: operacoes do dia (clique em barra do VOP Diario) ────────────────


class OperacaoDoDiaItem(BaseModel):
    """Operacao individual exibida no DrillDownSheet do dia."""

    operacao_id: str = Field(description="ID externo da operacao (Bitfin)")
    data_de_efetivacao: date
    cedente: str | None = Field(description="Nome do cedente quando disponivel")
    produto_sigla: str | None
    produto_nome: str | None
    ua_id: int | None
    ua_nome: str | None
    valor_bruto: float = Field(description="Operacao.total_bruto em BRL")
    taxa: float | None = Field(description="Taxa de juros (% am ou aa, conforme operacao)")
    prazo_medio: float | None = Field(description="Prazo medio real em dias")


class QuebraDiaPorDimensao(BaseModel):
    """Quebra do VOP do dia por uma dimensao (produto ou ua)."""

    label: str
    valor: float
    share_pct: float = Field(description="Participacao % no VOP do dia")


class CedenteMtdItem(BaseModel):
    """Linha da tabela narrativa de cedentes MTD.

    Granularidade: cedente principal de cada operacao (MIN(cedente_nome) dos
    titulos da op, via wh_operacao_item x wh_titulo_snapshot). Aceita-se
    aproximacao quando uma op tem multiplos cedentes — todo o valor da op
    vai pro principal. Refinamento por titulo (valor_base) fica como
    follow-up se virar bloqueador.

    Status:
      - "novo":       cedente sem operacoes anteriores ao MTD (primeira_op
                      cai dentro do mes corrente).
      - "sumido":     cedente teve operacao no mes anterior mas zero no MTD
                      (volume_mtd, n_op, dias_mtd, taxa_media = None).
      - "recorrente": teve operacoes antes do MTD E tem no MTD.
    """

    cedente_nome: str
    cedente_id: int | None = Field(
        description=(
            "ID quando disponivel (cedente_cliente_id de wh_titulo_snapshot). "
            "Pode ser None se o cedente aparece so com nome."
        )
    )
    volume_mtd: float | None = Field(
        description="VOP MTD do cedente em BRL. None quando 'sumido'."
    )
    delta_vs_mes_ant_pct: float | None = Field(
        description=(
            "Variacao percentual vs MTD same-DU do mes anterior. "
            "-100% quando 'sumido', None quando nao ha base (cedente 'novo')."
        )
    )
    status: str = Field(description='"novo" | "recorrente" | "sumido"')
    n_op: int | None = Field(
        description="Numero de operacoes no MTD. None quando 'sumido'."
    )
    dias_mtd: int | None = Field(
        description="Dias distintos com operacao no MTD. None quando 'sumido'."
    )
    taxa_media: float | None = Field(
        description=(
            "Taxa media ponderada por valor das ops do MTD do cedente. "
            "None quando 'sumido'."
        )
    )
    primeira_op: date | None = Field(
        description="Data da 1a operacao historica do cedente."
    )
    ultima_op: date | None = Field(
        description="Data da ultima operacao historica do cedente."
    )
    # Campos opt-in de operacoes4 (regime caixa). None quando service nao
    # enriqueceu o item — preserva backwards compat com /bi/operacoes3.
    receita_total: float | None = Field(
        default=None,
        description=(
            "Receita MTD alocada ao cedente proporcional ao seu volume "
            "(regime caixa: 4 buckets de wh_operacao). None quando "
            "'sumido' ou nao enriquecido."
        ),
    )
    yield_pct: float | None = Field(
        default=None,
        description=(
            "receita_total / volume_mtd em % a.m. None quando 'sumido' "
            "ou nao enriquecido."
        ),
    )


class CedentesMtdData(BaseModel):
    """Bundle da Tabela narrativa de cedentes MTD."""

    cedentes: list[CedenteMtdItem]
    total: int = Field(description="Numero total de cedentes na lista.")
    mes_label: str = Field(description="Ex.: 'mai/26' (mes corrente).")


class OperacoesDoDiaData(BaseModel):
    """Drill 'operacoes do dia X' — conteudo do DrillDownSheet.

    Servido pelo endpoint `/bi/operacoes2/operacoes-do-dia?data=YYYY-MM-DD`.
    Aplica todos os filtros globais (UA, produto, etc) e escopo de tenant.
    """

    data: date
    vop_do_dia: float
    n_operacoes: int
    ticket_medio: float
    taxa_media: float | None
    prazo_medio: float | None

    operacoes: list[OperacaoDoDiaItem]
    por_produto: list[QuebraDiaPorDimensao]
    por_ua: list[QuebraDiaPorDimensao]
