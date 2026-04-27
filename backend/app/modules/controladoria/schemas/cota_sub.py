"""Pydantic schemas — Controladoria · Cota Sub.

Espelho do contrato TypeScript em
`frontend/src/app/(app)/controladoria/cota-sub/page.tsx::VariacaoDiariaResponse`.

A planilha origem (VariacaoDeCota_Preenchida.xlsx, aba Analise) decompoe a
variacao do PL Sub Jr entre D-1 e D0 por categoria de ativo + atribui as
parcelas a "causas" (apropriacao vs movimento).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

PlCategoriaKey = Literal[
    "compromissada",
    "mezanino",
    "senior",
    "titulos_publicos",
    "fundos_di",
    "dc",
    "op_estruturadas",
    "outros_ativos",
    "pdd",
    "cpr",
    "tesouraria",
]


class PlCategoria(BaseModel):
    """Linha 16/20 da planilha — uma categoria de ativo no PL."""

    key:    PlCategoriaKey
    label:  str
    d1:     Decimal = Field(description="Valor em D-1 (R$)")
    d0:     Decimal = Field(description="Valor em D0 (R$)")
    delta:  Decimal = Field(description="d0 - d1")
    source: str     = Field(description="Tabela canonica origem")


DecomposicaoSinal = Literal["ganho", "prejuizo", "neutro"]


class DecomposicaoItem(BaseModel):
    """Painel C27:D35 da planilha — atribuicao da variacao a uma causa."""

    key:   str
    label: str
    valor: Decimal
    sinal: DecomposicaoSinal


class ApropriacaoDcLinha(BaseModel):
    """Bloco 'a vencer' OU 'vencidos' da aba APROPRIACAO DC."""

    estoque_d1:  Decimal = Field(description="Estoque D-1 (valor presente)")
    aquisicoes:  Decimal = Field(description="Aquisicoes consolidadas no periodo")
    liquidados:  Decimal = Field(description="Liquidados no periodo (negativo = saida)")
    estoque_d0:  Decimal = Field(description="Estoque D0 (valor presente)")
    apropriacao: Decimal = Field(
        description="estoque_d0 - (estoque_d1 + aquisicoes + liquidados)",
    )


class ApropriacaoDc(BaseModel):
    """Aba APROPRIACAO DC inteira (a vencer + vencidos + total)."""

    a_vencer: ApropriacaoDcLinha
    vencidos: ApropriacaoDcLinha
    total:    Decimal = Field(description="a_vencer.apropriacao + vencidos.apropriacao")


class CprMovimentoItem(BaseModel):
    """Linha individual da aba CPR (descricao + valor)."""

    descricao: str
    valor:     Decimal


class CprDetalhado(BaseModel):
    """Aba CPR completa — listas de receber/pagar D-1 e D0 + variacao."""

    receber_d1: list[CprMovimentoItem]
    receber_d0: list[CprMovimentoItem]
    pagar_d1:   list[CprMovimentoItem]
    pagar_d0:   list[CprMovimentoItem]
    total_d1:   Decimal = Field(description="receber - pagar em D-1")
    total_d0:   Decimal = Field(description="receber - pagar em D0")
    variacao:   Decimal = Field(description="total_d0 - total_d1 (entra como D30 da Analise)")


class VariacaoDiariaResponse(BaseModel):
    """Resposta do endpoint GET /controladoria/cota-sub/variacao-diaria."""

    fundo_id:           str       = Field(description="UUID da Unidade Administrativa")
    fundo_nome:         str
    data:               date      = Field(description="D0 (dia analisado)")
    data_anterior:      date      = Field(description="D-1 (dia util anterior)")
    pl_d1:              Decimal
    pl_d0:              Decimal
    pl_delta:           Decimal   = Field(description="pl_d0 - pl_d1")
    pl_delta_pct:       Decimal   = Field(description="pl_delta / pl_d1 (fracao decimal)")
    categorias:         list[PlCategoria]
    decomposicao:       list[DecomposicaoItem]
    decomposicao_total: Decimal
    divergencia:        Decimal   = Field(description="decomposicao_total - pl_delta (deve ser ~0)")
    apropriacao_dc:     ApropriacaoDc
    cpr_detalhado:      CprDetalhado
