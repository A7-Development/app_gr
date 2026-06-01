"""Pydantic schemas — Controladoria · Detalhamento do dia (o painel dos 60%).

Um card por AREA do balanco (Ativo e Passivo), cada um com o resumo de 1 linha
da sua tool + o delta (impacto no PL Sub) + a chave do drill. E o nivel
intermediario entre o balancete (a posicao) e o drill (a prova papel-a-papel):
"o que cada area fez hoje", montado das tools, clicavel pro fundo.

Determinismo total — orquestra as tools que ja existem, zero LLM.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class AreaDetalhe(BaseModel):
    """Uma area do balanco com o resumo da sua tool."""

    key:       str = Field(description="Identificador da area (= drill_key quando dráável).")
    label:     str
    grupo:     Literal["ativo", "passivo"]
    delta:     Decimal = Field(description="Impacto no PL Sub da area (da linha de balanco).")
    resumo:    str = Field(description="1 linha factual da tool (ex.: 'resultado +8k · giro 1M neutro').")
    drill_key: str | None = Field(default=None, description="Linha a abrir no clique (None = sem drill).")
    severidade: Literal["rotina", "atencao"] = "rotina"


class DetalhamentoDiaResponse(BaseModel):
    """Detalhamento do dia: uma area por card, na otica do PL Sub.

    Ordenado por grupo (Ativo primeiro) e, dentro do grupo, por |delta|.
    """

    fundo_id:      str
    fundo_nome:    str
    data:          date
    data_anterior: date | None = None
    areas:         list[AreaDetalhe] = Field(default_factory=list)
