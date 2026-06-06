"""Pydantic schemas — Controladoria · Resumo do dia (waterfall + grupos).

O contrato do `GET /controladoria/cota-sub/variacao/resumo` — a aba "Resumo do
dia" do redesign 2026-06-01. Substitui o trabalho do `variacao/headline` (que
mostrava Ativo-Passivo) por uma decomposicao CAUSAL da variacao da Cota Sub,
organizada pelos GRUPOS DE BALANCO, com impacto giro-limpo.

Tres blocos, todos 100% estruturados (zero LLM — o chat-investigador entra so
sob demanda):

  1. WATERFALL  — PL Sub D-1 (MEC) -> 6 transformacoes -> PL Sub D0 (MEC).
                  Cada transformacao = 1 grupo de balanco, impacto giro-limpo.
  2. GRUPOS     — os mesmos 6 grupos, com suas linhas (detalhamento por balanco).
  3. ATENCOES   — mutacao silenciosa / pagamento sem provisao / WOP, cada uma
                  ancorada ao grupo-casa + drill + flag de investigavel.

Fechamento (regra dura, §14): Σ grupos.impacto_pl_sub == cota_delta (por
construcao — Disponibilidades e o plug). A reconciliacao compara cota_delta
(apresentada) com a variacao do MEC (oficial); o residuo e exposto SEMPRE.

Vocabulario canonico (alinhado com o balanco estrutural — um nome em todo lugar):
Direitos Creditorios · (-) PDD & WOP · Aplicacoes · Disponibilidades ·
Obrigacoes e Provisoes · Cotas Prioritarias.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# Os 6 grupos de topo do Resumo (= as 6 barras do waterfall). Espelham o balanco
# estrutural, com Direitos Creditorios e PDD & WOP ABERTOS como itens proprios
# (decisao 2026-06-01) e os demais grupos agregando suas linhas.
GrupoResumoKey = Literal[
    "direitos_creditorios",   # Carteira DC — resultado giro-limpo (carrego+mora-desconto+mutacao)
    "pdd_wop",                # (-) PDD & WOP — contra-ativo (constituicao/reversao + write-off)
    "aplicacoes",             # TPF + Op.Estruturadas(NC) + Fundos DI + Compromissada + Outros
    "disponibilidades",       # Tesouraria + Conta Corrente + Contas a Receber (lar do giro = plug)
    "obrigacoes_provisoes",   # Contas a Pagar + Obrigacoes com Cotistas
    "cotas_prioritarias",     # Cota Senior + Cota Mezanino
]

GrupoNatureza = Literal["ativo", "contra_ativo", "passivo"]

AtencaoTipo = Literal[
    "mutacao",                  # mudanca silenciosa de parametro de papel (VN/taxa/venc)
    "despesa_nao_provisionada", # pagamento de despesa acima da provisao, bateu na cota
    "write_off",                # titulos levados a WOP (saiu do estoque sem liquidacao)
    "capital",                  # aporte/resgate de cotista que diluiu/concentrou a Sub
    "reconciliacao",            # saldo da cota nao bate com o MEC
    "nao_reconhecido",          # lancamento que nenhuma fonte soube classificar
]


class GrupoResumoLinha(BaseModel):
    """Uma linha dentro de um grupo (o detalhamento por balanco, sub-nivel).

    Para 'direitos_creditorios' e 'pdd_wop' (itens abertos) a lista costuma ter
    1 linha (a propria) ou ficar vazia. Para os grupos agregados (aplicacoes,
    disponibilidades, etc.) traz as linhas-fonte do balanco (Titulos Publicos,
    Fundos DI, Tesouraria, ...), inclusive zeradas (prova de completude).
    """

    key:            str = Field(description="Chave da linha do balanco (= drill_key quando dravel).")
    label:          str
    impacto_pl_sub: Decimal = Field(description="Impacto giro-limpo no PL Sub (sinal de impacto).")
    resumo:         str = Field(default="", description="Contexto curto (ex.: 'rendimento R$0,3k', '↺ giro').")
    drill_key:      str | None = Field(default=None)
    severidade:     Literal["rotina", "atencao"] = "rotina"


class GrupoResumo(BaseModel):
    """Um dos 6 grupos de topo — 1 barra do waterfall + 1 bloco do detalhamento."""

    key:            GrupoResumoKey
    label:          str
    natureza:       GrupoNatureza
    impacto_pl_sub: Decimal = Field(
        description="Impacto giro-limpo no PL Sub (sinal de impacto: + ajudou a cota, "
                    "- pressionou). E a altura/direcao da barra no waterfall.",
    )
    resumo:         str = Field(description="1 linha factual do grupo (ex.: 'carrego + mora · giro neutro').")
    drill_key:      str | None = Field(default=None, description="Drill ao clicar (None = sem drill rico).")
    severidade:     Literal["rotina", "atencao"] = "rotina"
    linhas:         list[GrupoResumoLinha] = Field(
        default_factory=list,
        description="Sub-linhas do grupo (detalhamento por balanco). Vazia p/ itens atomicos.",
    )


class ReconciliacaoResumo(BaseModel):
    """A resposta a 'a variacao apresentada bate com o MEC?' — §14, sempre visivel."""

    variacao_apresentada: Decimal = Field(description="Σ grupos.impacto_pl_sub (= cota_delta calculado).")
    variacao_mec:         Decimal = Field(description="ΔPL Sub do MEC (QiTech, oficial).")
    residuo:              Decimal = Field(description="apresentada - MEC. Vira barra no waterfall se != 0.")
    fecha:                bool = Field(description="|residuo| < tolerancia (R$ 1).")
    # Saldo absoluto (a prova definitiva de nivel, secundaria a variacao do dia).
    residuo_saldo_d0:     Decimal = Field(
        default=Decimal("0"),
        description="calc_d0 - MEC_d0. ~0 = a cota bate em nivel (independente de lag de timing).",
    )


class AtencaoResumo(BaseModel):
    """Uma atencao do dia — ancorada ao grupo-casa, abre o drill, opcionalmente investigavel.

    NAO e uma categoria fora do balanco: e uma LENTE sobre um valor que ja esta
    no waterfall (a mutacao esta dentro de Direitos Creditorios, o WOP dentro de
    PDD & WOP, etc.). Nao soma duas vezes.
    """

    tipo:        AtencaoTipo
    descricao:   str = Field(description="Texto factual pt-BR (ex.: 'Mutacao silenciosa ALFA→SACADO12: taxa subiu').")
    valor:       Decimal = Field(description="Magnitude do sinal (R$).")
    grupo_key:   GrupoResumoKey | None = Field(default=None, description="Grupo-casa onde a atencao mora.")
    grupo_label: str = Field(default="", description="Label do grupo-casa (chip na faixa).")
    drill_key:   str | None = Field(default=None, description="Drill que mostra a evidencia.")
    investigavel: bool = Field(default=False, description="True = vale 'investigar' (chat — o porque exige cruzar tools).")


GiroCapitalTipo = Literal[
    "giro_carteira",      # compra/liquidacao de recebiveis (caixa <-> DC)
    "capital_cotista",    # aporte/resgate em cota prioritaria + obrigacoes com cotistas
    "capital_aplicacao",  # aplicacao/resgate em fundo DI
    "floating",           # liquidacoes em transito (Contas a Receber)
    "outros",             # compromissada (overnight) e afins
]


class GiroCapitalItem(BaseModel):
    """Um movimento NEUTRO do dia: movimentou caixa/posicao mas NAO afetou o PL Sub.

    E o que antes poluia as barras (giro de carteira, aporte/resgate, floating).
    Agora sai do waterfall e vem aqui como contexto — magnitude movimentada, com
    impacto 0 na cota. Soma das magnitudes != 0 e so a movimentacao bruta.
    """

    tipo:  GiroCapitalTipo
    label: str
    valor: Decimal = Field(description="Magnitude movimentada (com sinal). Impacto na cota = 0.")
    nota:  str = Field(default="")


class VariacaoResumoResponse(BaseModel):
    """GET /controladoria/cota-sub/variacao/resumo — a aba 'Resumo do dia'.

    Decomposicao causal da variacao da Cota Sub por grupo de balanco, com impacto
    giro-limpo, ancoras MEC e atencoes. Determinismo total (orquestra as tools;
    zero LLM). Fecha por construcao: Σ grupos.impacto_pl_sub == cota_delta.
    """

    fundo_id:      str
    fundo_nome:    str
    data:          date
    data_anterior: date

    # Valor UNITARIO da cota Sub no D0 (MEC valor_da_cota) — headline da band KPI.
    cota_valor_d0: Decimal | None = Field(default=None, description="Valor unitario da cota Sub em D0 (MEC).")

    # ── Ancoras do waterfall (MEC = oficial) ────────────────────────────────
    pl_sub_mec_d1: Decimal = Field(description="PL Sub D-1 lido do MEC (ancora inicial do waterfall).")
    pl_sub_mec_d0: Decimal = Field(description="PL Sub D0 lido do MEC (ancora final).")
    # PL Sub calculado (Σ Ativo - Σ Passivo) — base das transformacoes.
    pl_sub_calc_d1: Decimal
    pl_sub_calc_d0: Decimal
    cota_delta:     Decimal = Field(description="ΔPL Sub apresentado = Σ grupos.impacto_pl_sub.")

    # ── As 6 transformacoes (= barras do waterfall, blocos do detalhamento) ──
    grupos:        list[GrupoResumo] = Field(description="Os 6 grupos, na ordem do waterfall.")

    # ── Giro (contexto neutro, NAO entra na soma) ───────────────────────────
    giro_total:    Decimal = Field(
        default=Decimal("0"),
        description="Movimentacao de giro do dia (compra/liquidacao de recebivel + aplicacoes). "
                    "PL-neutro — mostrado como nota, nao como barra.",
    )

    # ── Giro e capital do dia (movimentos NEUTROS, lista informativa) ────────
    giro_capital:  list[GiroCapitalItem] = Field(
        default_factory=list,
        description="Movimentos que movimentaram caixa/posicao mas NAO afetaram o PL Sub "
                    "(compra/liquidacao de carteira, aporte/resgate de cotista, aplicacao DI, "
                    "floating). Contexto, fora do waterfall — cada um com impacto 0 na cota.",
    )

    # ── Reconciliacao MEC + atencoes ────────────────────────────────────────
    reconciliacao: ReconciliacaoResumo
    atencoes:      list[AtencaoResumo] = Field(default_factory=list)
