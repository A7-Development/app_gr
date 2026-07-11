"""Parametros versionados do motor de deteccao (PR 3 do rating).

Contrato sob teste: DEFAULTS cobrem tabela vazia; versao mais alta por nome
vence (append-only, padrao premise_set); catalogo de sinais semeado com os
codigos fechados 2026-07-10.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.modules.risco.models.deteccao import DeteccaoParametro
from app.modules.risco.services.deteccao_parametros import (
    DEFAULTS,
    carregar_parametros,
)

pytestmark = pytest.mark.asyncio


async def test_defaults_cobrem_tabela_vazia() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(DeteccaoParametro))
        await db.commit()
        params = await carregar_parametros(db)
    assert params == DEFAULTS
    assert params["fgp_min_eventos"] == 3
    assert params["agencia_matriz"] == "00001"


async def test_versao_mais_alta_vence() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(DeteccaoParametro))
        db.add(
            DeteccaoParametro(
                nome="cnv90_min_sacados", valor=10, version=1, criado_por="test"
            )
        )
        db.add(
            DeteccaoParametro(
                nome="cnv90_min_sacados",
                valor=15,
                version=2,
                motivo="recalibracao de teste",
                criado_por="test",
            )
        )
        await db.commit()
        params = await carregar_parametros(db)
        await db.execute(delete(DeteccaoParametro))
        await db.commit()
    assert params["cnv90_min_sacados"] == 15
    # nomes sem linha na tabela continuam nos defaults
    assert params["fgp_min_estabilidade"] == DEFAULTS["fgp_min_estabilidade"]


def test_catalogo_sinais_seed_migration() -> None:
    """Codigos do catalogo v3 (fechado 2026-07-10) presentes no seed da
    migration. Checagem estatica do arquivo — o conftest TRUNCATE derruba o
    seed do DB de teste, entao o contrato vive no proprio script."""
    from pathlib import Path

    versions = Path(__file__).resolve().parents[3] / "alembic" / "versions"
    mig = "\n".join(
        f.read_text(encoding="utf-8")
        for f in (
            versions / "d7f2a9c4e1b8_deteccao_sinal_parametro.py",
            versions / "f2c7d4a9e3b1_rating_liquidacao.py",
        )
    )
    esperados = {
        "PRC-01", "PRC-02", "PRC-03", "PRC-04",
        "CNV-01", "CNV-02", "CNV-90",
        "FGP-01", "MEC-01", "MEC-02", "MEC-03",
    }
    faltam = {c for c in esperados if f'"{c}"' not in mig}
    assert not faltam, f"seed do catalogo incompleto: faltam {faltam}"
    for parametro in DEFAULTS:
        assert f'"{parametro}"' in mig, f"parametro {parametro} sem seed na migration"
