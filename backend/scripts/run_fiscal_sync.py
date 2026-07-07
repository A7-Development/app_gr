"""Roda o drain fiscal (landing zone -> wh_nfe/wh_cte) para UM tenant.

Espelha `run_cobranca_sync.py`: o job do scheduler spawna ESTE script como
subprocess detached — o backfill inicial (~29k XMLs) e CPU-bound e nao pode
rodar no event loop do gr-api.

Uso:
    .venv/bin/python -m scripts.run_fiscal_sync <tenant_id>
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

import app.shared.identity.tenant  # noqa: F401  -- registra `tenants` (FK)
from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.fiscal.etl import sync_fiscal


async def _main(tenant_id: UUID) -> None:
    async with AsyncSessionLocal() as db:
        res = await sync_fiscal(db, tenant_id=tenant_id)
    print(f"[fiscal-sync] {tenant_id}: {res.as_dict()}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("uso: python -m scripts.run_fiscal_sync <tenant_id>")
    asyncio.run(_main(UUID(sys.argv[1])))
