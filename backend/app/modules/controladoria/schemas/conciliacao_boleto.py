"""Pydantic schemas — Controladoria · Conciliacao de boletos (Banco Cobrador).

Resposta da conciliacao carteira Bitfin x banco cobrador (item 2 da Entrega 3):
resumo consolidado por status + linhas titulo-a-titulo. O front segmenta as
linhas por status (Conciliado / Div. valor / Div. vencimento / So em BITFIN /
So em banco) e aplica filtros especificos do tenant (ex.: excluir FAT de
cedentes Pedreira na A7 — regra de front, nao do motor).

Silver-only (§13.2.1): a conciliacao le wh_titulo x wh_boleto.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

StatusConciliacao = Literal[
    "conciliado",
    "divergencia_valor",
    "divergencia_vencimento",
    "so_em_bitfin",
    "enviado_nao_confirmado",
    "so_em_banco",
]


class ResumoStatus(BaseModel):
    """Linha do resumo consolidado do dia, por status."""

    status: StatusConciliacao
    quantidade: int = Field(description="Quantidade de titulos/boletos no status.")
    percentual: float = Field(description="% sobre o total de linhas (0-100).")
    valor_bitfin: Decimal = Field(description="Soma do valor liquido (carteira).")
    valor_banco: Decimal = Field(description="Soma do valor do boleto (banco).")
    diferenca: Decimal = Field(description="valor_banco - valor_bitfin.")


class LinhaConciliacaoSchema(BaseModel):
    """Uma linha titulo-a-titulo da conciliacao."""

    status: StatusConciliacao
    numero: str = Field(description="Numero do documento/titulo (chave de cruzamento).")
    nosso_numero: str | None = Field(
        default=None, description="Nosso numero do banco (lado boleto)."
    )
    valor_bitfin: Decimal | None = Field(default=None, description="Valor liquido do titulo.")
    valor_banco: Decimal | None = Field(default=None, description="Valor do boleto.")
    diferenca_valor: Decimal | None = Field(
        default=None, description="valor_banco - valor_bitfin (quando ambos existem)."
    )
    venc_bitfin: date | None = Field(default=None, description="Vencimento do titulo (SP).")
    venc_banco: date | None = Field(default=None, description="Vencimento do boleto.")
    data_operacao: date | None = Field(
        default=None, description="Data da operacao (efetivacao da cessao, SP)."
    )
    diferenca_dias: int | None = Field(
        default=None, description="venc_banco - venc_bitfin em dias (quando ambos existem)."
    )
    produto: str | None = Field(default=None, description="Produto/papel (FAT/CBV/DMS/CBS).")
    banco: str | None = Field(default=None, description="Banco cobrador (lado banco).")
    cedente_documento: str | None = Field(
        default=None, description="CNPJ do cedente — para filtros de tenant no front."
    )
    cedente_nome: str | None = Field(default=None, description="Nome do cedente.")
    ua_id: int | None = Field(
        default=None, description="UA (Unidade Administrativa) — escopo. Null em 'só em banco'."
    )
    ua_nome: str | None = Field(default=None, description="Nome amigável da UA.")
    situacao_titulo: int | None = Field(
        default=None,
        description="Situacao do titulo no wh_titulo (codigo Bitfin: 0=aberto, "
        "1=liquidado, 5=recomprado). Preenchida apenas em 'so_em_banco' — "
        "liquidado/recomprado com boleto ativo = cabe pedido de baixa. None em "
        "'so_em_banco' = titulo inexistente no warehouse.",
    )
    enviado_em: date | None = Field(
        default=None,
        description="Data de geracao da remessa de registro (apenas em "
        "'enviado_nao_confirmado') — base do aging 'aguardando ha N dias'.",
    )
    protesto_tipo: str | None = Field(
        default=None,
        description="Ultimo evento do pipeline de protesto do boleto: "
        "protesto_instruido | encaminhado_cartorio | protesto_sustado | "
        "retirado_cartorio. None = sem protesto.",
    )
    protesto_em: date | None = Field(
        default=None, description="Data do ultimo evento de protesto."
    )


class FrescorBanco(BaseModel):
    """Frescor do retorno de UM banco cobrador."""

    banco: str = Field(description="Banco cobrador (bradesco/vortx/bmp/itau).")
    retorno_ate: date = Field(
        description="Data do ultimo evento de RETORNO processado deste banco "
        "(max data_ocorrencia na timeline). Banco parado fica visivel aqui "
        "mesmo com o frescor global em dia."
    )


class ConciliacaoBancoCobradorResponse(BaseModel):
    """Resultado da conciliacao estado-vs-estado (carteira atual x cobranca)."""

    cobranca_atualizada_ate: date | None = Field(
        default=None,
        description="Frescor do lado banco: data do ultimo evento de cobranca "
        "processado. A carteira BITFIN e 'agora'.",
    )
    frescor_bancos: list[FrescorBanco] = Field(
        default_factory=list, description="Frescor do retorno por banco."
    )
    titulos_abertos: int = Field(description="Titulos abertos elegiveis a boleto.")
    boletos_ativos: int = Field(description="Boletos ativos (cobranca vigente).")
    conciliados: int = Field(description="Quantidade conciliada (sem divergencia).")
    resumo: list[ResumoStatus] = Field(description="Consolidado por status.")
    linhas: list[LinhaConciliacaoSchema] = Field(description="Detalhe titulo-a-titulo.")
