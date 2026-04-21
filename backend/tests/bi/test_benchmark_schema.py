"""Smoke test -- ponte postgres_fdw `cvm_remote.*` expoe as tabelas v0.3.0.

Valida que, apos o deploy do ETL v0.3.0 + reimport do foreign schema no
`gr_db`, as 3 tabelas novas representativas respondem a `SELECT COUNT(*)`
via `cvm_remote`:

- `tab_x_1_1` -- cotistas por tipo de investidor x classe (36 colunas)
- `tab_x_2`   -- NAV por subclasse (valor de cota, qt em circulacao)
- `tab_x_7`   -- garantias em direitos creditorios

Objetivo: pegar regressao de ponte FDW (IMPORT FOREIGN SCHEMA esqueceu
alguma tabela, permissao do role do `gr_db` no `cvm_benchmark` esta
quebrada, etc). Nao e teste de conteudo -- so de conectividade.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.database import AsyncSessionLocal

_TABELAS_V0_3_0 = ("tab_x_1_1", "tab_x_2", "tab_x_7")


@pytest.mark.asyncio
@pytest.mark.parametrize("tabela", _TABELAS_V0_3_0)
async def test_cvm_remote_fdw_expoe_tabela(tabela: str) -> None:
    """SELECT COUNT(*) via cvm_remote.<tabela> retorna inteiro >= 0."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(f"SELECT count(*) FROM cvm_remote.{tabela}"))
        total = r.scalar_one()
    assert isinstance(total, int)
    assert total >= 0
