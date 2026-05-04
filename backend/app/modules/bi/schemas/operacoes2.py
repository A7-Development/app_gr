"""Schemas da L2 Operacoes2 (refatoracao 2026-05-03).

A pagina gira em torno de 5 indicadores-chave (VOP, Taxa, Prazo, Produto Top,
Receita Contratada) expostos num KPI Strip global, e 4 abas que sao lentes de
aprofundamento:

- Aba 1: Volume & Ritmo
- Aba 2: Produtos & Pricing      (futuro)
- Aba 3: Receita                 (futuro)
- Aba 4: Cedentes & Concentracao (futuro — depende de cedente_id em wh_operacao)

Cada endpoint retorna `BIResponse[<data>]` com proveniencia.

Decisao de design (2026-05-03):
- 1 delta por KPI, label "MoM" forcado (vs periodo imediatamente anterior de
  mesmo tamanho — o backend reutiliza `_shift_period_back`).
- Sparklines sao SEMPRE 12M corridos terminando em `periodo_fim` (ou hoje).
- Campos que dependem de `wh_dim_dia_util` (ritmo do mes, pace diario,
  heatmap dow x semana) retornam `None` quando a tabela esta vazia (degraded
  mode). Frontend renderiza placeholder.
"""

from pydantic import BaseModel, Field

from app.modules.bi.schemas.common import Point


# ─── KPI Strip ──────────────────────────────────────────────────────────────


class KpiCellNumeric(BaseModel):
    """Celula generica do strip (VOP, Taxa, Prazo, Receita).

    Strip dual (Opcao 4 paradigma 2026-05-03): cada cell carrega valor do
    PERIODO + valor do MES CORRENTE em paralelo. Frontend renderiza ambos.
    `delta_pct` compara periodo atual vs periodo imediatamente anterior de
    mesmo tamanho. Sparkline e sempre 12M.
    """

    valor: float
    unidade: str = Field(description="'BRL' | '%' | 'dias'")
    delta_pct: float | None
    sparkline_12m: list[Point]
    # Mes corrente — agregado limitado a [1o dia mes do periodo_fim, periodo_fim].
    mes_corrente_valor: float
    mes_corrente_label: str = Field(description="Ex.: 'Maio/2026'")


class KpiCellProduto(BaseModel):
    """Celula especifica do KPI #4 (Produto Top).

    `share_pct` em escala 0-100. `delta_share_pp` e variacao em pontos
    percentuais da fatia de mercado interna (vs periodo anterior).
    `sparkline_share_12m` mostra a evolucao do share_pct mes a mes (12M).

    Strip dual: produto top do MES pode ser diferente do produto top do
    PERIODO (Faturizacao dominou 12M, mas DM virou lider em maio). Frontend
    pode mostrar ambos lado a lado.
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


class MesCorrenteVsMedia(BaseModel):
    """Mes corrente vs media 12M (mini-stat #3 do rodape)."""

    vop_corrente: float
    media_12m: float
    pct: float = Field(description="(corrente / media_12m - 1) * 100")


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


class AcumuladoDiarioPonto(BaseModel):
    du_index: int
    corrente: float
    anterior: float


class PaceDiario(BaseModel):
    """Linha 2 Card sidekick — VOP medio por DU corrente vs mes anterior.

    DEPENDE de `wh_dim_dia_util`. `null` em degraded mode.
    """

    vop_du_corrente: float
    vop_du_anterior: float
    delta_pct: float | None


class KpiSecundario(BaseModel):
    """Linha 3 — KPI scalar com delta MoM (sem sparkline)."""

    valor: float
    delta_pct: float | None


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


class HeatmapDowSemanaPonto(BaseModel):
    """Linha 5 Card A — celula do heatmap dow x semana."""

    dow: int = Field(description="1=Segunda...5=Sexta")
    semana_do_mes: int = Field(description="1..5")
    vop_medio: float
    n_ops: int


class DiaSemanaResumo(BaseModel):
    """Linha 5 Card B — barra simples por dia da semana."""

    dow: int
    nome: str
    vop_medio: float
    n_ops_medio: float
    pct_total_semana: float


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
    mes_corrente_vs_media: MesCorrenteVsMedia | None

    # Linha 2 (degraded quando DU vazio)
    ritmo: RitmoMesCorrente | None
    pace_diario: PaceDiario | None

    # Linha 3
    kpis_secundarios: KpisSecundariosVolume

    # Linha 4 — quebras (UA na L1, Produto na L4)
    por_ua: list[QuebraDimensaoLinha]
    por_produto: list[QuebraDimensaoLinha]

    # Linha 5
    heatmap_dow_semana: list[HeatmapDowSemanaPonto]  # vazio em degraded
    por_dia_semana: list[DiaSemanaResumo]


# Resolve forward ref de RitmoMesCorrente.acumulado_dia_a_dia
RitmoMesCorrente.model_rebuild()
