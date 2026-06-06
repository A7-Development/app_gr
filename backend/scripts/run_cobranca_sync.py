"""Roda o ciclo manual de cobranca para UM tenant (coleta -> decode -> project).

Usado pelo botao "Sincronizar" da pagina banco-cobrador: o endpoint spawna ESTE
script como subprocess detached (`python -m scripts.run_cobranca_sync <tenant>`)
em vez de rodar inline. Motivo: o ciclo e CPU-bound (~45s: materializa 35k
eventos + 35k ocorrencias + 100k titulos) -- rodar no event loop do gr-api
congelaria todos os outros requests, e rodar numa thread esbarraria no engine
async global preso ao loop do processo. O subprocess isola tudo (proprio loop,
proprio engine, proprio pool).

Uso:
    .venv/bin/python -m scripts.run_cobranca_sync <tenant_id>
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

import app.shared.identity.tenant  # noqa: F401  -- registra `tenants` (FK)
from app.modules.integracoes.adapters.cobranca.etl import run_cobranca_manual_sync


async def _main(tenant_id: UUID) -> None:
    res = await run_cobranca_manual_sync(tenant_id)
    print(f"[cobranca-sync] {tenant_id}: {res}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("uso: python -m scripts.run_cobranca_sync <tenant_id>")
    asyncio.run(_main(UUID(sys.argv[1])))
