"""Pydantic schemas — Controladoria · Movimento de Aplicacoes (grupo Aplicacoes).

O grupo "Aplicacoes" do balanco Cota Sub tem 5 linhas. Materialidade real
(REALINVEST, 2026-05): quase tudo e Fundos DI EXTERNO (ITAU SOBERANO, onde o
fundo estaciona caixa ocioso, swing diario de ±R$ 250k). TPF e imaterial (~R$
12k), Compromissada e zero, Outros Ativos e so a linha PDD (excluida do balanco).
Op. Estruturadas (NC) tem auditor PROPRIO (auditor_notas_comerciais) e fica fora.

Este tracker abre a variacao do grupo:
  - Fundos DI externo (DEEP): por fundo, decompoe ΔSaldo em CAPITAL
    (aplicacao/resgate = Δqtd x cota) vs VALORIZACAO (rendimento DI = residuo).
    Cruzamento LIMPO: a aplicacao/resgate aparece nominal no demonstrativo de
    caixa ("Aplicacao no Fundo X" / "Resgate do Fundo X").
  - TPF / Compromissada / Outros (LIGHT): so ΔSaldo, sinalizado se material.

Fundos INTERNOS (REALINVEST A VENCER/VENCIDOS) sao a carteira DC representada
como cotas — EXCLUIDOS (contabilizados no DC; ver _is_fundo_externo).

Silver-only (§13.2.1): wh_posicao_cota_fundo + wh_posicao_renda_fixa +
wh_posicao_compromissada + wh_posicao_outros_ativos + wh_movimento_caixa (cross-ref).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

TipoMovimentoFundo = Literal["aplicacao", "resgate", "so_valorizacao"]


class MovimentoFundoDI(BaseModel):
    """Movimento de UM fundo DI externo entre D-1 e D0, decomposto."""

    fundo_nome:        str
    valor_d1:          Decimal = Field(description="valor_liquido em D-1.")
    valor_d0:          Decimal = Field(description="valor_liquido em D0.")
    delta_valor:       Decimal = Field(description="valor_d0 - valor_d1.")

    aplicacao_resgate: Decimal = Field(
        description="CAPITAL = Δquantidade x cota_d0. >0 = aplicou caixa (aumentou posicao); "
                    "<0 = resgatou (caixa entrou)."
    )
    valorizacao:       Decimal = Field(
        description="Rendimento DI do dia = delta_valor - aplicacao_resgate (residuo, liquido de IR)."
    )
    tipo:              TipoMovimentoFundo

    # Cross-ref LIMPO com o demonstrativo de caixa.
    caixa_aplicacao:   Decimal = Field(description="Σ saidas 'Aplicacao no Fundo X' no demonstrativo (D0). <=0.")
    caixa_resgate:     Decimal = Field(description="Σ entradas 'Resgate do Fundo X' no demonstrativo (D0). >=0.")
    caixa_confirma:    bool = Field(
        description="True quando o net de caixa (aplicacao+resgate) bate o capital da posicao (Δqtdxcota)."
    )
    bullet:            str = Field(description="1 linha factual: fundo, capital vs valorizacao, R$.")


class LinhaAplicacaoMenor(BaseModel):
    """Linha menor do grupo (TPF / Compromissada / Outros) — so ΔSaldo."""

    linha:    str = Field(description="key: titulos_publicos | compromissada | outros_ativos.")
    label:    str
    valor_d1: Decimal
    valor_d0: Decimal
    delta:    Decimal
    nota:     str = Field(description="Contexto: imaterial / vazia / movimento relevante.")


class ConferenciaAplicacoesResponse(BaseModel):
    """Movimento do grupo Aplicacoes de um dia (D0), exceto Op. Estruturadas (NC).

    Deep em Fundos DI externo (capital vs valorizacao, cruzado com o demonstrativo
    de caixa); light nas linhas menores (TPF/Compromissada/Outros, so ΔSaldo).
    """

    fundo_id:              str
    fundo_nome:            str
    data:                  date
    data_anterior:         date | None = None

    fundos_di:             list[MovimentoFundoDI] = Field(default_factory=list)
    delta_fundos_di:       Decimal = Field(description="Σ delta_valor dos fundos DI externos.")
    total_capital_liquido: Decimal = Field(
        description="Σ aplicacao_resgate (net de caixa aplicado/resgatado nos fundos no dia). "
                    ">0 = aplicou liquido; <0 = resgatou liquido."
    )
    total_valorizacao:     Decimal = Field(description="Σ valorizacao (rendimento DI do dia).")

    outras_linhas:         list[LinhaAplicacaoMenor] = Field(
        default_factory=list, description="TPF / Compromissada / Outros — so ΔSaldo (geralmente imaterial).",
    )
    delta_aplicacoes_total: Decimal = Field(
        description="ΔSaldo do grupo Aplicacoes inteiro (Fundos DI + linhas menores), exceto NC."
    )
