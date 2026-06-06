"""Pydantic schemas — Controladoria · Headline da Variacao da Cota Sub.

O "read de 10 segundos" da pagina Cota Sub, montado SO de campos estruturados
(zero LLM). Orquestra as tools que ja existem e entrega 3 blocos:

  1. VEREDITO  — Δ da cota + reconciliacao + nº de atencoes (o glance de 5s).
  2. DRIVERS   — o que moveu a cota, ranqueado por impacto LIMPO (giro separado
                 do resultado, via resultado_do_dia). NAO os deltas crus do
                 balanco — senao o giro de R$ 1M afoga o sinal (licao 13/05).
  3. FLAGS     — o que vigiar, com R$ (mutacao, despesa nao provisionada, evento
                 de capital, residuo, nao-reconhecidos). Empurra ate o usuario.

Determinismo total: a "inteligencia" e o transform de ranking (giro fora) +
coleta de flags. Reproduzivel, auditavel (§14), barato. O LLM (chat) so entra
depois, sob demanda, pra investigar o que o headline aponta.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# Chave do driver -> liga ao drill correspondente no clique.
DriverKey = Literal[
    "resultado_carteira",      # carrego + mora + antecipada - desconto + mutacao (DC, giro-limpo)
    "carrego_prioritarias",    # remuneracao Sr/Mez que a Sub paga
    "despesa",                 # apropriacao de despesa (Contas a Pagar)
    "despesa_nao_provisionada",# excesso de pagamento s/ provisao (bate na cota)
    "pdd",                     # constituicao/reversao de PDD
    "capital_cotista",         # aporte/resgate (neutro no PL Sub; muda o % de subordinacao)
    "aplicacoes",              # rendimento DI / TPF
    "notas_comerciais",        # carrego/eventos de NC
    "giro_reclassificacao",    # movimentacao DC<->caixa<->DI (NEUTRO, contexto)
]

FlagTipo = Literal[
    "mutacao", "despesa_nao_provisionada", "capital", "reconciliacao", "nao_reconhecido",
]


class HeadlineDriver(BaseModel):
    """Um motor da variacao da cota, ja na otica do PL Sub (sinal de impacto)."""

    key:            DriverKey
    label:          str
    impacto_pl_sub: Decimal = Field(description="+ aumentou a cota Sub, - reduziu. R$.")
    detalhe:        str = Field(description="1 linha factual (ex.: 'carrego R$34,2k - mutacao R$27,7k').")
    drill_key:      str | None = Field(default=None, description="Linha de balanco a abrir no clique (None = sem drill).")
    severidade:     Literal["rotina", "atencao"] = "rotina"


class HeadlineFlag(BaseModel):
    """Um ponto de atencao do dia, com R$, que sobe ate o usuario."""

    tipo:        FlagTipo
    descricao:   str
    valor:       Decimal = Field(description="Magnitude do sinal. R$.")
    drill_key:   str | None = Field(default=None, description="Drill que mostra a evidencia.")
    investigavel: bool = Field(
        default=False, description="True = vale um 'investigar' (chat) — o porque exige cruzar tools.",
    )


class VariacaoHeadlineResponse(BaseModel):
    """O headline de 10s da variacao da Cota Sub de um dia (D0).

    Veredito + drivers (ranqueados por impacto limpo) + flags. Tudo estruturado,
    montado das tools (compute_drill_dc, compute_movimento_cotas,
    compute_movimento_contas_a_pagar, compute_balanco_estrutural). Zero LLM.
    """

    fundo_id:       str
    fundo_nome:     str
    data:           date
    data_anterior:  date | None = None

    # ── Veredito (glance de 5s) ─────────────────────────────────────────────
    cota_sub_d1:    Decimal
    cota_sub_d0:    Decimal
    cota_sub_delta: Decimal = Field(description="ΔPL Sub Jr (o numero que estamos explicando).")
    # A equacao do balanco (a verdade concreta, sem abstracao): Ativo - Passivo = Sub.
    delta_ativo:    Decimal = Field(description="Δ total do Ativo (giro JA netado no total).")
    delta_passivo:  Decimal = Field(description="Δ total do Passivo (inclui Contas a Pagar + Cotas Sr/Mez).")
    # O que IMPORTA: o residuo do SALDO (D0 absoluto). Se ~0, a cota BATE com o
    # MEC. O residuo do MOVIMENTO (delta) pode estar FORA so por lag de timing do
    # dia anterior (gap que abre num dia e fecha no outro) — secundario.
    reconciliacao_saldo:   Decimal = Field(description="Residuo do SALDO: calc_d0 - MEC_d0. ~0 = a cota bate.")
    reconciliacao_residuo: Decimal = Field(description="Residuo do MOVIMENTO (delta D-1->D0). Lag de timing, secundario.")
    reconciliacao_ok:      bool = Field(description="True quando o SALDO bate (|residuo_saldo| pequeno).")
    n_atencao:      int = Field(description="Quantidade de flags (atencoes do dia).")

    # ── Drivers (o que moveu, ranqueado por |impacto| limpo) ────────────────
    drivers:        list[HeadlineDriver] = Field(default_factory=list)

    # ── Giro (contexto, NAO e driver de resultado — PL-neutro) ──────────────
    giro_aquisicoes:  Decimal = Field(default=Decimal("0"), description="Σ VP comprado no dia (papeis novos).")
    giro_liquidacoes: Decimal = Field(default=Decimal("0"), description="Σ VP liquidado (papeis que sairam).")

    # ── Flags (o que vigiar) ────────────────────────────────────────────────
    flags:          list[HeadlineFlag] = Field(default_factory=list)
