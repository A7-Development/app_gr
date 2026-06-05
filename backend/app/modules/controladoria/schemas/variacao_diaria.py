"""Controladoria · Cota Sub — serie diaria da variacao da cota (competencia).

Master do master-detail da aba "Resumo do dia": uma entrada por dia do mes.
Variacao = Δ do PL Sub MEC (oficial) entre dias uteis consecutivos com snapshot.
O drill (waterfall) decompoe o dia selecionado e expoe a reconciliacao calc vs MEC.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class VariacaoDiariaSeriePonto(BaseModel):
    """Um ponto da serie diaria (um dia-calendario da competencia)."""

    data: date
    """Dia (ISO YYYY-MM-DD)."""
    variacao_cota: Decimal | None
    """Δ R$ do PL Sub MEC no dia (vs dia util anterior). None = sem apuracao."""
    variacao_pct: Decimal | None
    """Δ% sobre o PL Sub MEC do dia util anterior. None quando nao ha D-1."""
    eh_dia_util: bool
    """False em sab/dom (label dim no eixo X)."""
    eh_futuro: bool
    """Dia > hoje (sem barra)."""
