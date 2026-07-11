"""Loader dos parametros versionados do motor de deteccao.

Fonte unica dos thresholds/janelas/regras estruturais que eram constantes
hardcoded (decisao Ricardo 2026-07-10 — zero hardcode): a versao ATIVA de
cada parametro e a de maior `version` (append-only, padrao premise_set).

Consumo tipico (1 select por run de scoring):

    params = await carregar_parametros(db)
    minimo = int(params["fgp_min_eventos"])

`DEFAULTS` documenta o valor de nascenca de cada parametro e serve de
fallback quando a tabela ainda nao foi semeada (ambiente de teste vazio) —
producao SEMPRE resolve pela tabela.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.risco.models.deteccao import DeteccaoParametro

logger = logging.getLogger(__name__)

# Valores de nascenca (seed da migration d7f2a9c4e1b8). Mudanca de valor em
# producao = INSERT de nova versao na tabela, nunca editar este dict.
DEFAULTS: dict[str, Any] = {
    # Agencia-matriz (0001): concentra liquidacao eletronica do pais inteiro
    # em bancos digitais/atacado — cidade da matriz nao e praca (S1 falso).
    "agencia_matriz": "00001",
    # FGP-01: minimo de eventos pagos do sacado para o fingerprint pontuar.
    "fgp_min_eventos": 3,
    # FGP-01: participacao minima do banco dominante (habito estavel).
    "fgp_min_estabilidade": 0.8,
    # CNV-90 (composto critico): minimo de sacados de cidades divergentes
    # compartilhando a mesma agencia fisica.
    "cnv90_min_sacados": 10,
    # Janela (dias) da contagem de agencia compartilhada (CNV-01/02).
    "cnv_janela_dias": 365,
}


async def carregar_parametros(db: AsyncSession) -> dict[str, Any]:
    """Versao ativa (maior version) de cada parametro, sobre os DEFAULTS."""
    params = dict(DEFAULTS)
    rows = (
        await db.execute(
            select(DeteccaoParametro).order_by(
                DeteccaoParametro.nome, DeteccaoParametro.version
            )
        )
    ).scalars()
    for row in rows:  # ordenado por version asc — a ultima vence
        params[row.nome] = row.valor
    return params
