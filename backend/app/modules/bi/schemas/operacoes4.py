"""Schemas da L2 Operacoes4 (Mes Corrente · operacoes — controladoria).

Pagina `/bi/operacoes4` reorienta `operacoes3` pra responder perguntas que
chegam da equipe de controladoria sobre o mes em curso. Estrutura visual em
8 camadas (L1..L8), detalhada no SPEC do handoff:

- L1 KPIs (4 cards: VOP, Receita, Taxa, Prazo)
- L2 Hero Volume (VOP diario + card Projecao&Gap)
- L3 Receitas NOVO (Composicao por tipo + Yield efetivo por DU)
- L4 Mix de produtos (Waterfall + Taxa por produto)
- L5 Cedentes (tabela + 3 MovementCards)
- L6 Pricing NOVO (Histogramas taxa + prazo, baseline DU-paridade)
- L7 Tabela narrativa diaria NOVO
- L8 Decomposicao avancada (colapsada, 4 cards)

DECISAO DE REGIME (2026-05-20):
Receita opera em REGIME CAIXA — `wh_operacao` somando componentes discretas
(`total_de_juros`, `total_dos_comunicados_de_cessao`, ...). Valor diverge do
DRE oficial (regime competencia em `wh_dre_mensal`) mas mantem granularidade
diaria — pre-requisito da L3 (YieldChart por DU) e L7 (Receita/Yield por
DU). Multa, mora, cobranca e aditivo NAO aparecem nesta visao (sao eventos
pos-cessao; nao existem em `wh_operacao`).

4 BUCKETS DE RECEITA (regime caixa, Bitfin):
- DESAGIO              = total_de_juros
- TARIFA_CESSAO        = total_dos_comunicados_de_cessao
- TARIFAS_OPERACIONAIS = CF + CFI + RB + DD
  (total_das_consultas_financeiras + total_das_consultas_fiscais +
   total_dos_registros_bancarios + total_dos_documentos_digitais)
- OUTRAS               = total_de_ad_valorem + total_de_rebate (zero em prod
                         hoje; placeholder)

IOF (total_de_iof) e PASSTHROUGH — fica fora do yield e da composicao.

YIELD EFETIVO:
  yield_pct = receita_total / vop_bruto, em % a.m. equivalente
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class Operacoes4ReceitaTipo(StrEnum):
    """Bucket de receita exibido na composicao da L3.

    Ordem do enum reflete a ordem visual canonica (do maior ao menor share
    tipico): Desagio domina (~85%), Tarifa de Cessao e Tarifas Operacionais
    sao perifericas, Outras e placeholder.
    """

    DESAGIO = "desagio"
    TARIFA_CESSAO = "tarifa_cessao"
    TARIFAS_OPERACIONAIS = "tarifas_operacionais"
    OUTRAS = "outras"


class Operacoes4ReceitaComposicaoItem(BaseModel):
    """1 linha da composicao da receita MTD (L3 esquerda).

    `share_pct` em escala 0-100, soma 100,0% (com tolerancia de arredondamento
    de 0,1pp). `delta_pct` compara o valor do bucket no MTD corrente vs o
    mesmo bucket nos mesmos N DUs do mes anterior (paridade DU). None quando
    nao ha base no mes anterior.

    `flag_atypical` marca movimentos que merecem atencao visual no frontend:
    |delta_pct| > 20% OU (share_pct > 5% E delta_pct anormal). Determinado
    no service, nao no frontend.
    """

    tipo: Operacoes4ReceitaTipo
    valor: Decimal = Field(description="Receita do bucket no MTD em BRL")
    share_pct: float = Field(description="% do total MTD (0-100)")
    delta_pct: float | None = Field(
        description="vs mesmo N DUs do mes anterior (paridade DU)"
    )
    flag_atypical: bool = Field(
        default=False,
        description="True quando movimento merece atencao no frontend",
    )


class Operacoes4YieldPonto(BaseModel):
    """Ponto da serie de yield efetivo por DU (L3 direita).

    `yield_pct` = receita_do_DU / vop_bruto_do_DU, em % a.m. equivalente.
    `yield_parity_pct` = mesma metrica no DU correspondente do mes anterior
    (paridade DU). None quando o DU correspondente nao existe no mes anterior.

    `today` marca o DU corrente — frontend renderiza ponto destacado.
    """

    du: int = Field(description="Numero do dia util no mes corrente (1..N)")
    yield_pct: float = Field(description="Yield do DU em % a.m.")
    yield_parity_pct: float | None = Field(
        description="Yield no DU correspondente do mes anterior"
    )
    today: bool = Field(default=False)


class Operacoes4Mover(BaseModel):
    """Bucket que mais cresceu ou caiu vs paridade DU.

    Exibido como pill no rodape do card YieldChart (L3 direita).
    """

    tipo: Operacoes4ReceitaTipo
    delta_pct: float = Field(description="Delta vs paridade em % (signed)")
    valor: Decimal = Field(description="Valor MTD em BRL")


class Operacoes4Movers(BaseModel):
    """Dois movers: bucket que cresceu mais e o que caiu mais."""

    cresceu: Operacoes4Mover | None = Field(
        description="Bucket com maior delta positivo; None se nenhum positivo"
    )
    caiu: Operacoes4Mover | None = Field(
        description="Bucket com maior delta negativo; None se nenhum negativo"
    )


class Operacoes4LensReceitasData(BaseModel):
    """Bundle do endpoint `/bi/operacoes4/lens-receitas`.

    Alimenta as duas metades da L3 (Composicao + YieldChart) + movers. Toda
    query do service passa por `_apply_filters` com escopo de tenant.
    """

    total_mtd: Decimal = Field(description="Receita total MTD em BRL")
    total_parity: Decimal = Field(
        description="Receita total nos mesmos N DUs do mes anterior"
    )
    delta_pct: float | None = Field(
        description="(total_mtd - total_parity) / total_parity * 100"
    )

    composicao: list[Operacoes4ReceitaComposicaoItem] = Field(
        description="Sempre 4 itens (1 por bucket), na ordem do enum"
    )

    yield_du: list[Operacoes4YieldPonto] = Field(
        description="Serie de yield por DU do mes corrente"
    )
    yield_wavg: float = Field(
        description="Yield medio ponderado por VOP no MTD (% a.m.)"
    )
    yield_delta_pp: float | None = Field(
        description="Delta de yield_wavg vs mes anterior em pontos percentuais"
    )
    yield_parity_wavg: float = Field(
        description="Yield wavg no mes anterior nos mesmos N DUs"
    )

    movers: Operacoes4Movers

    mes_label: str = Field(description="Ex.: 'mai/26'")
    du_decorridos: int
    du_totais_mes: int
    du_disponivel: bool = Field(
        description="False = wh_dim_dia_util vazia (degraded mode)"
    )


class Operacoes4TaxaBucket(BaseModel):
    """1 faixa do histograma de taxas MTD (L3 card 1).

    `vop_mtd` e o volume (total_bruto) das operacoes cuja taxa cai na faixa,
    no MTD do mes corrente. `is_tail` marca a faixa de cauda (>3,5%) — pintada
    em vermelho no frontend.
    """

    label: str = Field(description="Ex.: '<2,0', '2,0-2,5', '>3,5'")
    vop_mtd: Decimal = Field(description="VOP MTD das operacoes na faixa (BRL)")
    is_tail: bool = Field(default=False)


class Operacoes4LensTaxasData(BaseModel):
    """Bundle do endpoint `/bi/operacoes4/lens-taxas`.

    Alimenta a L3 card 1 (Distribuicao de taxas · MTD). Histograma de 5 faixas
    fixas ponderadas por VOP MTD + taxa media ponderada (wavg, identica ao
    termometro) + mediana ponderada por VOP. `delta_pct` compara o wavg MTD vs
    o wavg dos mesmos N DUs do mes anterior (paridade DU) — None quando nao ha
    base. Toda query passa por `_apply_filters` com escopo de tenant (§7.2).
    """

    histograma: list[Operacoes4TaxaBucket] = Field(
        description="Sempre 5 faixas, na ordem crescente de taxa"
    )
    wavg_pct: float = Field(
        description="Taxa media ponderada por VOP no MTD (% a.m.)"
    )
    mediana_pct: float = Field(
        description="Taxa mediana ponderada por VOP no MTD (% a.m.)"
    )
    delta_pct: float | None = Field(
        description="wavg MTD vs wavg dos mesmos N DUs do mes anterior (%)"
    )
    n_operacoes: int = Field(description="Operacoes efetivadas no MTD")

    mes_label: str = Field(description="Ex.: 'jun/26'")
    du_decorridos: int
    du_totais_mes: int
    du_disponivel: bool = Field(
        description="False = wh_dim_dia_util vazia (degraded mode)"
    )


class Operacoes4ReceitaPorDia(BaseModel):
    """Receita + yield agregados por dia (1 linha por data calendario).

    Helper que pode ser consultado isoladamente; tambem alimenta a extensao
    de `VopDiarioPonto` com colunas Receita/Yield na tabela narrativa diaria
    (L7).
    """

    data: date
    receita: Decimal = Field(description="Receita do dia em BRL (4 buckets)")
    yield_pct: float | None = Field(
        description="receita / vop_bruto. None se vop=0 no dia."
    )


# ─── Diaria enriquecida (L7) ───────────────────────────────────────────────


class Operacoes4DiariaPonto(BaseModel):
    """Ponto da serie narrativa diaria (L7) — 1 linha por DU do mes corrente.

    Reusa o shape canonico `VopDiarioPonto` adicionando colunas
    receita+yield+outlier flag. So dias uteis com VOP > 0 aparecem (dias
    sem operacao caem do payload — caller projeta sobre o calendario do
    mes inteiro se precisar).
    """

    du: int = Field(description="Index do dia util no mes corrente (1..N)")
    data: date
    vop: float
    receita: float = Field(description="Receita do dia (4 buckets, regime caixa)")
    yield_pct: float | None
    today: bool = Field(default=False)
    delta_par_pct: float | None = Field(
        default=None,
        description="VOP vs DU correspondente do mes anterior (paridade). None se sem base.",
    )
    outlier: bool = Field(
        default=False,
        description=(
            "True quando o dia esta fora da curva pelo criterio default "
            "(P5/P95 do MTD OU |Δ DU-par| > 50%)."
        ),
    )


class Operacoes4DiariaData(BaseModel):
    """Bundle da serie narrativa diaria do mes corrente (L7)."""

    pontos: list[Operacoes4DiariaPonto]
    mes_label: str
    mes_inicio: date
    mes_fim: date
    du_decorridos: int
    du_totais_mes: int
    du_disponivel: bool
