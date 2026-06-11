"""Schemas da pagina Receitas (3 metodos sobre o catalogo de receitas).

Metodos (decisao 2026-06-12, nenhum elimina o outro):
    caixa       -> wh_receita_caixa (desagio na SAIDA do titulo) + eventos
    competencia -> wh_receita_operacional completo (desagio na efetivacao)
    acruo       -> wh_receita_acruo_dia (curva D+1 DU) + eventos

"Eventos" = familias mora/prorrogacao/recompra/tarifa_servico/repasse/
financeira do wh_receita_operacional — identicas nos 3 metodos.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Metodo = Literal["caixa", "competencia", "acruo"]


class ReceitasKpis(BaseModel):
    total: Decimal
    desagio: Decimal = Field(description="Natureza DESAGIO (bloco operacao)")
    mora: Decimal = Field(
        description="JUROS_MORA + MULTA_MORA + ENCARGO_NEGOCIADO (todas as familias)"
    )
    tarifas: Decimal = Field(description="TARIFA (operacao + servico)")
    recompra_encargos: Decimal = Field(description="Familia recompra (juros+multa+desagio)")


class SerieMensalPonto(BaseModel):
    competencia: date
    por_familia: dict[str, Decimal]
    total: Decimal


class ComposicaoNatureza(BaseModel):
    natureza: str
    valor: Decimal


class PonteMetodos(BaseModel):
    """Os 3 totais do MESMO periodo/filtros + deltas explicados (§14.6)."""

    caixa: Decimal
    competencia: Decimal
    acruo: Decimal
    delta_competencia_caixa: Decimal = Field(
        description="= desagio+tarifas de titulos operados no periodo e ainda nao liquidados (em aberto)"
    )
    delta_competencia_acruo: Decimal = Field(
        description="= saldo a apropriar (curva que corre fora do periodo)"
    )


class ReceitasResumoResponse(BaseModel):
    metodo: Metodo
    kpis: ReceitasKpis
    serie_mensal: list[SerieMensalPonto]
    composicao_natureza: list[ComposicaoNatureza]
    ponte: PonteMetodos


class ReceitaDetalheLinha(BaseModel):
    familia: str
    stream: str = Field(description="stream_key (competencia) ou evento (caixa/acruo)")
    natureza: str
    qtd: int
    valor: Decimal


class ReceitasDetalheResponse(BaseModel):
    metodo: Metodo
    linhas: list[ReceitaDetalheLinha]
    total: Decimal


class ReceitaCedenteLinha(BaseModel):
    cedente_nome: str
    cedente_documento: str | None
    desagio: Decimal
    mora: Decimal
    tarifas: Decimal
    demais: Decimal
    total: Decimal
    qtd: int


class ReceitasCedentesResponse(BaseModel):
    metodo: Metodo
    linhas: list[ReceitaCedenteLinha]
    total: Decimal


class ReceitaTituloLinha(BaseModel):
    data: date
    titulo_id: int | None
    documento: str | None
    cedente_nome: str | None
    natureza: str
    valor: Decimal
    valor_referencia_regua: Decimal | None = None


class ReceitasTitulosResponse(BaseModel):
    metodo: Metodo
    familia: str
    stream: str
    linhas: list[ReceitaTituloLinha]
    total: Decimal
    qtd: int


class DescontoMoraCedente(BaseModel):
    cedente_nome: str
    cedente_documento: str | None
    regua: Decimal = Field(description="Σ regua contratual (referencia)")
    cobrado: Decimal = Field(description="Σ efetivamente lancado/cobrado")
    desconto: Decimal = Field(description="regua - cobrado (negativo = cobrou acima)")
    perdoes_totais: int = Field(description="linhas com cobrado=0 e regua>0")
    qtd: int


class ReceitasConferenciasResponse(BaseModel):
    competencia_de: date
    competencia_ate: date
    desconto_mora: list[DescontoMoraCedente]
    total_regua: Decimal
    total_cobrado: Decimal
    total_desconto: Decimal
    total_perdoes: int
