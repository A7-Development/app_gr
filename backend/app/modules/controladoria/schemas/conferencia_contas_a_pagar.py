"""Pydantic schemas — Controladoria · Movimento de Contas a Pagar (CPR < 0).

A linha "Contas a Pagar" do balanco Cota Sub = provisoes de despesa (CPR negativo
em wh_cpr_movimento). O lado de saida/despesa do fundo. Tres dinamicas:

  - APROPRIACAO: a provisao de taxa CRESCE dia a dia (accrual de custodia/gestao/
    administracao ate pagar). Despesa do dia, ainda nao paga.
  - BAIXA: a provisao some/reduz. Pode ser PAGAMENTO (zera contra saida de caixa)
    ou ESTORNO/WASH (zera sem caixa — lancamento+estorno).
  - PAGAMENTO NAO PROVISIONADO: saida de caixa de despesa que NUNCA passou pelo
    CPR (tarifas bancarias `0770`, debitos inesperados) — sinalizado.

Classificacao do pagamento pelo CODIGO `historico` do extrato (dicionario
levantado em toda a historia 2021-2026):
  - despesa com codigo proprio (debito direto da administradora SINGULARE):
    0887 custodia, 0869/0870 adm, 0941 banco liquidante, 0917 ANBIMA, 0919 CVM,
    0918 distribuicao, 3053 registradora, 3051/3057 auditoria, 3045 IOF,
    3043/0920 IR, 0948/0915/0916/0914 reembolsos, 0603 reg.cobranca, 0943 SELIC.
  - 0770 = TARIFA DE TED -> sempre NAO provisionada.
  - 0307 = TED generico -> despesa SO quando contrapartida e fornecedor
    (nao-cedente, nao-emitente de NC, nao o proprio fundo): ONBOARD (consultoria/
    cobranca), AUSTIN RATING, Confiance (auditoria), etc.
  - internos (fora do escopo): 0902, 0123, 0835, 0950, 0875, 0859, estornos.

ARMADILHA (memoria): wh_cpr_movimento.valor = SALDO ACUMULADO por lote (pico,
nao soma). Tracking por delta de data_posicao. Datas de pagamento no TEXTO sao
erradas — usar so as colunas de data (data_lancamento do extrato).

Silver-only (§13.2.1): wh_cpr_movimento + wh_extrato_bancario.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

TipoMovimentoProvisao = Literal["apropriacao", "nova_provisao", "baixa", "quitada", "estavel"]
CanalPagamento = Literal["codigo_proprio", "tarifa_ted", "ted_fornecedor"]


class CprForaEscopo(BaseModel):
    """Item CPR<0 que NAO e despesa — capital de cotista, ajuste, nao classificado.

    Antes do classificador por natureza (2026-05-31) esses itens vazavam pra
    dentro da decomposicao de provisao como se fossem despesa (ex.: Cotas a
    Resgatar -R$3M era tratada como uma 'baixa de provisao'). Agora ficam fora
    do escopo de despesa e sao SINALIZADOS aqui, com a natureza e o auditor dono.
    """

    descricao: str = Field(description="Descricao normalizada do item CPR.")
    natureza:  str = Field(description="capital_cotista | ajuste_estorno | nao_classificado.")
    saldo_d0:  Decimal = Field(description="Saldo do item em D0 (com sinal).")
    dono:      str = Field(description="Auditor a quem pertence (ex.: 'cotas', 'reconciliacao').")


class MovimentoProvisao(BaseModel):
    """Movimento de UMA provisao de despesa (CPR<0) entre D-1 e D0."""

    descricao:  str = Field(description="Descricao normalizada (sem a data do texto).")
    saldo_d1:   Decimal = Field(description="Saldo da provisao em D-1 (<=0).")
    saldo_d0:   Decimal = Field(description="Saldo da provisao em D0 (<=0).")
    delta:      Decimal = Field(description="saldo_d0 - saldo_d1. <0 = apropriou (cresceu); >0 = baixou.")
    tipo:       TipoMovimentoProvisao


class PagamentoDespesa(BaseModel):
    """Um pagamento de despesa no caixa do dia (debito do extrato classificado)."""

    canal:        CanalPagamento
    historico:    str = Field(description="Codigo de transacao bancaria do extrato.")
    label:        str = Field(description="Tipo da despesa (do codigo) ou nome do fornecedor (TED).")
    contrapartida: str | None = Field(default=None, description="Nome da contraparte (TED a fornecedor).")
    valor:        Decimal = Field(description="Magnitude paga (R$ > 0).")
    provisionado: bool = Field(
        description="Tem provisao CPR compativel que baixou no dia? False = pagamento NAO provisionado."
    )


class ConferenciaContasAPagarResponse(BaseModel):
    """Movimento de Contas a Pagar de um dia (D0): provisoes (CPR<0) + pagamentos.

    Decompoe o ΔSaldo da linha Contas a Pagar em apropriacao (accrual) vs baixa
    (pagamento/estorno), e lista os pagamentos de despesa do caixa classificados
    por codigo. Pagamento sem provisao -> sinalizado.
    """

    fundo_id:        str
    fundo_nome:      str
    data:            date
    data_anterior:   date | None = None

    # ── Provisoes (CPR < 0, SO natureza despesa/imposto) ────────────────────
    # Filtrado por classify_cpr_nature: despesa_a_pagar + imposto_a_recolher.
    # Capital de cotista / ajuste / nao classificado saem para `fora_escopo`.
    saldo_cpr_d1:    Decimal = Field(description="Σ CPR<0 de DESPESA em D-1 (exclui capital de cotista).")
    saldo_cpr_d0:    Decimal = Field(description="Σ CPR<0 de DESPESA em D0.")
    delta_cpr:       Decimal = Field(description="saldo_cpr_d0 - saldo_cpr_d1 (= ΔSaldo da linha).")
    total_apropriacao: Decimal = Field(description="Σ provisao apropriada no dia (accrual; magnitude >0).")
    total_baixa:     Decimal = Field(description="Σ provisao baixada no dia (paga ou estornada; magnitude >0).")
    provisoes:       list[MovimentoProvisao] = Field(default_factory=list)

    # ── Pagamentos de despesa no caixa (D0) ─────────────────────────────────
    pagamentos:      list[PagamentoDespesa] = Field(default_factory=list)
    total_pago:      Decimal = Field(description="Σ pagamentos de despesa do dia (>0).")
    total_nao_provisionado: Decimal = Field(
        description="Σ pagamentos sem NENHUMA provisao compativel (tarifas + despesa inesperada). >0."
    )
    impacto_resultado_nao_provisionado: Decimal = Field(
        description="Despesa que bateu no PL Sub HOJE sem ter sido provisionada = "
                    "(excesso de pagamento sobre a provisao baixada) + (pagamentos sem provisao). "
                    ">0 reduz o PL Sub no dia. E o que explica quedas inesperadas da cota: a provisao "
                    "ja paga e neutra (apropriada antes), so o excesso/nao-provisionado bate agora. "
                    "= max(0, total_pago - total_nao_provisionado - total_baixa) + total_nao_provisionado."
    )

    # ── Fora do escopo de despesa (sinalizado, nao silenciado) ──────────────
    fora_escopo: list[CprForaEscopo] = Field(
        default_factory=list,
        description="Itens CPR<0 que NAO sao despesa (capital de cotista, ajuste, nao "
                    "classificado). Antes vazavam como 'provisao'; agora ficam de fora e "
                    "sao sinalizados com a natureza e o auditor dono. Lista vazia = dia limpo.",
    )
