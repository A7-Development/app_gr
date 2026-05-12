"""Pydantic schemas — Balancete Patrimonial Diario COSIF.

Espelha as dataclasses do `services/balancete_diario.py` para serializacao
HTTP. Frontend consome via hook `useBalanceteDiario`.

Design: backend/docs/atribuicao-cota-sub-cosif.md.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CosifNodeSchema(BaseModel):
    """Linha do balancete hierarquico COSIF."""

    codigo: str | None = Field(description="None = saldo nao classificado (pendente)")
    nome: str
    natureza: str = Field(description="D=Devedora, C=Credora, ?=pendente")
    nivel: int = Field(description="1-6 na arvore COSIF; 0 quando pendente")
    grupo: int = Field(description="1=Ativo, 4=Passivo, 6=PL, 8=Despesas; 0 quando pendente")
    parent_codigo: str | None
    d_minus_1: Decimal
    d_zero: Decimal
    delta: Decimal
    delta_pct: Decimal
    rows_classified: int = 0
    cosif_source: str = ""


class ClasseSrMezSubBreakdownSchema(BaseModel):
    """Quebra por classe Sr/Mez/Sub dentro de uma conta COSIF."""

    classe: str = Field(description="senior|mezanino|subordinado|compensacao|aporte")
    d_minus_1: Decimal
    d_zero: Decimal
    delta: Decimal


class ReconciliacaoSchema(BaseModel):
    """Equacao da Cota Sub: PL Total - cotas Sr - cotas Mez."""

    pl_total_d1: Decimal
    pl_total_d0: Decimal
    delta_pl_total: Decimal
    cotas_sr_emitidas_d1: Decimal
    cotas_sr_emitidas_d0: Decimal
    delta_cotas_sr: Decimal
    cotas_mez_emitidas_d1: Decimal
    cotas_mez_emitidas_d0: Decimal
    delta_cotas_mez: Decimal
    pl_cota_sub_d1: Decimal
    pl_cota_sub_d0: Decimal
    delta_pl_cota_sub_real: Decimal
    delta_pl_cota_sub_esperado: Decimal
    residuo: Decimal
    delta_pct_sobre_d1: Decimal


class PendenteEntrySchema(BaseModel):
    silver_origin: str
    identificador: str
    valor: Decimal


class CoberturaSchema(BaseModel):
    """Estatistica de classificacao."""

    total_rows: int
    rows_por_source: dict[str, int]
    valor_por_source: dict[str, Decimal]
    top_pendentes: list[PendenteEntrySchema]


class DataQualitySchema(BaseModel):
    """Qualidade do snapshot D-1 vs D0 (detecta ETL parcial)."""

    silvers_d1:           dict[str, int]
    silvers_d0:           dict[str, int]
    silvers_divergentes:  list[str]
    comparable:           bool
    reason:               str | None = None


class BalanceteResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fundo_id: UUID
    data_d_zero: date
    data_d_minus_1: date
    nodes: list[CosifNodeSchema]
    classe_breakdown_por_cosif: dict[str, list[ClasseSrMezSubBreakdownSchema]]
    reconciliacao: ReconciliacaoSchema
    cobertura: CoberturaSchema
    data_quality: DataQualitySchema


class CosifRowSchema(BaseModel):
    """Row do silver subjacente a uma conta COSIF (drill-down)."""

    silver_origin: str
    codigo: str | None = Field(description="Identificador no silver (codigo do papel, conta, etc.)")
    nome: str
    valor: Decimal
    quantidade: Decimal | None = None
    indexador: str | None = None
    cosif_source: str


class CosifRowsResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fundo_id: UUID
    data_posicao: date
    cosif_codigo: str
    cosif_nome: str
    total_valor: Decimal
    rows: list[CosifRowSchema]
