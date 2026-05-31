"""Pydantic schemas — Controladoria · Movimento de Nota Comercial (Op. Estruturadas).

A linha "Op. Estruturadas" do balanco Cota Sub = Notas Comerciais (nome_do_papel
NCPX/VCNC/PDDNC em wh_posicao_renda_fixa). Hoje aparece so como ΔSaldo mudo.

Este tracker e POSICAO-FIRST: a fonte autoritativa do que mexeu na NC e a
propria posicao (wh_posicao_renda_fixa), nao o caixa. Detecta por diff D-1 vs D0:

  - aquisicao  : codigo novo (ausente D-1, presente D0) -> valor_aplicado saiu do caixa
  - amortizacao: valor_bruto CAIU (liquido do carrego do dia) -> NC paga em parcela
  - quitacao   : codigo zerou/sumiu -> NC liquidada por inteiro
  - apropriacao: valor_bruto SUBIU -> so carrego (juros do dia), nao e evento de caixa

DESAFIO DO CAIXA (decisao 2026-05-31, confirmado em dado): a liquidacao da NC NAO
aparece como deposito do devedor no extrato. O devedor paga numa conta de
movimento (4532543) e o valor e transferido pra conciliacao (4532551) como
"TRANSF LIQU E BAIX A DEB REALINVEST FUNDO" — contrapartida = o PROPRIO fundo, e
generico a DC + NC. Por isso o extrato entra so como SINAL SOFT (indicio de valor
compativel), NUNCA como reconciliacao. A posicao manda.

Silver-only (§13.2.1): le wh_posicao_renda_fixa (+ wh_extrato_bancario soft).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

TipoMovimentoNC = Literal["aquisicao", "amortizacao", "quitacao", "apropriacao"]


class SinalExtratoNC(BaseModel):
    """Sinal SOFT do extrato (NAO autoritativo) — indicio de valor compativel.

    Para aquisicao: debito ao cnpj_emitente de valor ~ valor_aplicado.
    Para amortizacao/quitacao: credito 'TRANSF LIQU E BAIX' de valor compativel
    (a liquidacao da NC nao traz o devedor — vem como transferencia interna).
    """

    encontrado:      bool
    valor:           Decimal | None = None
    data_lancamento: date | None = None
    descricao:       str | None = None
    nota:            str = Field(
        default="",
        description="Por que e soft: liquidacao da NC vem como transferencia interna "
                    "do fundo, generica a DC+NC — confirma valor, nao o pagador.",
    )


class MovimentoNotaComercial(BaseModel):
    """Movimento de UMA nota comercial entre D-1 e D0 (posicao-first)."""

    codigo:          str = Field(description="Codigo da NC (C######).")
    emitente:        str
    cnpj_emitente:   str
    tipo:            TipoMovimentoNC
    data_vencimento: date | None = None

    valor_bruto_d1:  Decimal = Field(description="Posicao a mercado em D-1 (0 se nova).")
    valor_bruto_d0:  Decimal = Field(description="Posicao a mercado em D0 (0 se quitada).")
    delta_bruto:     Decimal = Field(description="valor_bruto_d0 - valor_bruto_d1.")
    valor_aplicado:  Decimal = Field(description="Valor original aplicado na NC (face).")

    # Evento de caixa IMPLICADO pela posicao (autoritativo).
    caixa_evento:    Decimal = Field(
        description="Caixa implicado: <0 saida (aquisicao = -valor_aplicado); "
                    ">0 entrada (amortizacao/quitacao = reducao liquida da posicao); "
                    "apropriacao=0 (carrego, nao e caixa). Amortizacao e LIQUIDA do "
                    "carrego do dia — o bruto recebido e ~ |delta| + carrego."
    )
    bullet:          str = Field(description="1 linha factual ancorada em R$ + codigo/emitente.")
    extrato_sinal:   SinalExtratoNC | None = Field(
        default=None, description="Sinal SOFT do extrato (indicio, nao prova)."
    )


class ConferenciaNotaComercialResponse(BaseModel):
    """Movimento das Notas Comerciais (Op. Estruturadas) de um dia (D0).

    Posicao-first: o ΔSaldo da linha 'Op. Estruturadas' do balanco e aberto em
    aquisicao / amortizacao / quitacao / apropriacao por codigo. O extrato entra
    so como sinal soft — a liquidacao da NC nao mostra o devedor (transferencia
    interna do fundo, generica a DC+NC).
    """

    fundo_id:           str
    fundo_nome:         str
    data:               date
    data_anterior:      date | None = None

    # Posicao consolidada (a linha 'Op. Estruturadas' do balanco).
    posicao_total_d1:   Decimal = Field(description="Σ valor_bruto das NCs em D-1.")
    posicao_total_d0:   Decimal = Field(description="Σ valor_bruto das NCs em D0.")
    delta_posicao:      Decimal = Field(description="posicao_total_d0 - posicao_total_d1.")
    n_notas_d0:         int

    # Decomposicao do delta por natureza de movimento.
    total_aquisicao:    Decimal = Field(description="Σ valor_aplicado das NCs novas (caixa que saiu).")
    total_amortizacao:  Decimal = Field(description="Σ reducao liquida (amortizacao + quitacao). >=0.")
    total_apropriacao:  Decimal = Field(description="Σ carrego do dia (juros das NCs que ficaram).")

    movimentos:         list[MovimentoNotaComercial] = Field(
        default_factory=list,
        description="Movimentos com evento (aquisicao/amortizacao/quitacao/apropriacao "
                    "material). NCs sem mudanca relevante sao omitidas.",
    )
