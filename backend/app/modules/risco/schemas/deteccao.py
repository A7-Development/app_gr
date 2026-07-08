"""Pydantic schemas of the detection/curation API (modulo risco)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.risco.models import CuradoriaTagValor


class LiquidacaoCuradoriaRow(BaseModel):
    """One curation row — every liquidation event, score or not."""

    liquidacao_id: UUID
    titulo_id: int
    titulo_numero: str | None = None
    canal: str
    evidencia: str | None = None
    data_evento: datetime
    # Snapshot de Titulo.Situacao (dicionario: 1 Liq Normal, 2 Cartorio,
    # 3 Baixado, 5 Recomprado, 7 Recuperacao, 9 Perda).
    situacao_titulo: int | None = None
    valor: float | None = None
    cedente_nome: str | None = None
    cedente_documento: str | None = None
    produto_sigla: str | None = None
    # Nome completo do produto (regra: nunca abreviar em superficie de UI).
    produto_nome: str | None = None
    sacado_nome: str | None = None
    sacado_documento: str | None = None
    local_pagamento: str | None = None
    pago_na_agencia_cliente: bool | None = None
    pago_na_praca_cliente: bool | None = None
    pago_fora_praca_sacado: bool | None = None
    score: float | None = None
    fatores: list[dict[str, Any]] | None = None
    regra_dura: bool | None = None
    regra_dura_motivo: str | None = None
    tag_vigente: str | None = None
    tag_nota: str | None = None
    tag_autor: str | None = None
    tag_em: datetime | None = None
    candidato_lastro: bool = False
    # Conclusoes legiveis do sistema ("qual foi o bad"), mais severa primeiro.
    sinais: list[str] = []


class LiquidacaoCuradoriaPage(BaseModel):
    total: int
    page: int
    page_size: int
    rows: list[LiquidacaoCuradoriaRow]


class MemoriaItem(BaseModel):
    label: str
    valor: str
    destaque: bool = False


class MemoriaSecao(BaseModel):
    titulo: str
    itens: list[MemoriaItem]


class MemoriaLiquidacao(BaseModel):
    """Memoria de calculo completa de uma liquidacao (drawer da curadoria)."""

    liquidacao_id: UUID
    titulo_numero: str | None
    cedente_nome: str | None
    regra_dura: bool
    regra_dura_motivo: str | None
    score: float | None
    fatores: list[dict[str, Any]] | None
    secoes: list[MemoriaSecao]


class CuradoriaTagCreate(BaseModel):
    tag: CuradoriaTagValor
    nota: str | None = Field(default=None, max_length=512)


class CuradoriaTagOut(BaseModel):
    id: UUID
    liquidacao_id: UUID
    tag: CuradoriaTagValor
    nota: str | None
    created_at: datetime


class ModeloVersaoOut(BaseModel):
    id: UUID
    versao: int
    metrics: dict[str, Any] | None
    n_amostras: int | None
    n_positivos: int | None
    trained_at: datetime
    notas: str | None
    ativa: bool


class ModeloOut(BaseModel):
    id: UUID
    nome: str
    alvo: str
    tipo: str
    unidade: str
    descricao: str | None
    versao_ativa: int | None
    versoes: list[ModeloVersaoOut]


class TreinoRequest(BaseModel):
    janela_dias: int = Field(default=365, ge=90, le=1830)
    oot_dias: int = Field(default=60, ge=14, le=365)


class TreinoResult(BaseModel):
    modelo: str
    versao: int
    versao_id: UUID
    metrics: dict[str, Any]
    n_positivos: int
    ativa: bool


class ScoringResult(BaseModel):
    modelo: str
    versao: int | None
    eventos_avaliados: int
    scores_gravados: int
    regra_dura: int
    elapsed_seconds: float
