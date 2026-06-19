"""Pydantic schemas — Controladoria · Movimento de Cotas (passivo de cotistas).

A lente do lado COTISTA/PATRIMONIO do balanco Cota Sub. Cobre:

  1. **Cotas Prioritarias (Senior + Mezanino)** — na otica da Sub Jr sao PASSIVO.
     Cada classe variou por CAPITAL (aporte/resgate do cotista) e/ou VALORIZACAO
     (remuneracao da cota no dia = carrego que a Sub PAGA). Reusa
     compute_decomposicao_classes_mec (wh_mec_evolucao_cotas).
  2. **Obrigacoes com Cotistas** — a linha nova do balanco (CPR natureza
     capital_cotista): Cotas a Resgatar (resgate solicitado, ainda nao pago),
     Aporte (capital recebido nao integralizado / a devolver), Resgate de Cotas.

Por que importa pro PL Sub: a Sub e o residual (PL_Sub = Ativo - Senior -
Mezanino - Obrigacoes - Contas a Pagar). Toda remuneracao das prioritarias e
custo da Sub (reduz o residual). Ja o APORTE/RESGATE de capital numa prioritaria
e NEUTRO no PL Sub em R$ (o caixa entra/sai na mesma medida que o passivo varia)
— dilui/concentra o % de subordinacao, nao o valor. Toda obrigacao com cotista
que cresce reduz o residual. Esta e a unica lente que fecha o passivo.

Silver-only (§13.2.1): wh_mec_evolucao_cotas + wh_cpr_movimento.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

ClasseCota = Literal["sub_jr", "mezanino", "senior"]
ClassificacaoClasse = Literal["aporte", "resgate", "apenas_valorizacao"]
TipoObrigacao = Literal["nova", "aumento", "reducao", "quitada"]


class ClasseCotaMovimento(BaseModel):
    """ΔPL de UMA classe de cota, decomposto em capital vs valorizacao."""

    classe:         ClasseCota
    label:          str
    patrimonio_d1:  Decimal
    patrimonio_d0:  Decimal
    delta_pl:       Decimal = Field(description="patrimonio_d0 - patrimonio_d1.")
    valor_cota_d1:  Decimal
    valor_cota_d0:  Decimal
    delta_quantidade: Decimal = Field(description="Δ qtd de cotas (capta/resgata cotistas).")
    efeito_capital: Decimal = Field(
        description="Fluxo de cotistas no dia (entradas-saidas+aporte-retirada do MEC). "
                    ">0 aporte, <0 resgate."
    )
    efeito_valorizacao: Decimal = Field(
        description="ΔPL - efeito_capital = remuneracao/custo da cota no dia (carrego)."
    )
    classificacao:  ClassificacaoClasse
    impacto_pl_sub: Decimal = Field(
        description="Impacto no PL Sub Jr em R$. Prioritaria (Sr/Mez): SO o carrego "
                    "(valorizacao) impacta -> impacto = -efeito_valorizacao. O capital "
                    "(aporte/resgate) e NEUTRO (entra/sai do caixa na mesma medida; "
                    "dilui o % de subordinacao, nao o valor). A propria Sub Jr: "
                    "impacto = delta_pl (e o PL que estamos explicando)."
    )


class ObrigacaoCotista(BaseModel):
    """Movimento de UMA obrigacao com cotista (CPR capital_cotista) D-1 -> D0."""

    descricao: str = Field(description="Cotas a Resgatar | Aporte | Resgate de Cotas | ...")
    saldo_d1:  Decimal
    saldo_d0:  Decimal
    delta:     Decimal = Field(description="saldo_d0 - saldo_d1. Com sinal (capital <= 0).")
    tipo:      TipoObrigacao


class ConferenciaCotasResponse(BaseModel):
    """Movimento do passivo de cotistas de um dia (D0): prioritarias + obrigacoes.

    Fecha o lado passivo/patrimonio do balanco Cota Sub: a remuneracao e o capital
    das Cotas Prioritarias (Senior/Mezanino) + as Obrigacoes com Cotistas (CPR
    capital_cotista). Tudo na otica do PL Sub Jr (residual).
    """

    fundo_id:       str
    fundo_nome:     str
    data:           date
    data_anterior:  date | None = None

    # ── Classes de cota (Sub Jr / Mezanino / Senior) ────────────────────────
    classes: list[ClasseCotaMovimento] = Field(default_factory=list)
    custo_prioritarias_valorizacao: Decimal = Field(
        description="Σ efeito_valorizacao das prioritarias (Sr+Mez) = carrego que a Sub PAGA no dia. "
                    ">0 reduz o PL Sub."
    )
    capital_liquido_prioritarias: Decimal = Field(
        description="Σ efeito_capital das prioritarias (Sr+Mez). >0 = aporte (NEUTRO no "
                    "PL Sub em R$; muda so o % de subordinacao)."
    )
    capital_liquido_sub: Decimal = Field(
        default=Decimal("0"),
        description="efeito_capital da PROPRIA cota Sub (aporte/resgate do cotista subordinado). "
                    ">0 = aporte. NEUTRO na RENTABILIDADE (valor da cota) — entra caixa e cota "
                    "juntos —, mas AUMENTA o PL Sub em R$. NAO e resultado: deve ser segregado "
                    "do cota_delta (senao vaza pro plug de Disponibilidades)."
    )
    resultado_sub: Decimal = Field(
        default=Decimal("0"),
        description="efeito_valorizacao da cota Sub = rentabilidade do dia em R$ (= delta_pl - "
                    "capital_liquido_sub). E o resultado real que o waterfall explica."
    )

    # ── Obrigacoes com Cotistas (CPR capital_cotista) ───────────────────────
    obrigacoes:          list[ObrigacaoCotista] = Field(default_factory=list)
    obrigacoes_saldo_d0: Decimal = Field(description="Σ saldo capital_cotista em D0 (linha Obrigacoes com Cotistas).")
    obrigacoes_delta:    Decimal = Field(description="Δ da linha Obrigacoes com Cotistas (D0 - D-1).")
