"""Projeta wh_boleto_evento -> wh_boleto_vigente (Fatia 3 do rebuild).

Re-deriva o estado vigente de todos os boletos a partir da timeline. Idempotente
(reescreve a vigente do tenant). Rode apos o backfill de eventos.

Uso (de backend/):
    .venv/bin/python scripts/project_boleto_vigente.py                # todos os tenants
    .venv/bin/python scripts/project_boleto_vigente.py <tenant_id> [banco]
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

from sqlalchemy import select

import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.cobranca.project_vigente import (
    project_tenant_vigente,
)
from app.warehouse.boleto_evento import BoletoEvento


async def main() -> None:
    args = sys.argv[1:]
    tenant_arg = UUID(args[0]) if args else None
    banco = args[1] if len(args) > 1 else None

    async with AsyncSessionLocal() as db:
        if tenant_arg is not None:
            tenants = [tenant_arg]
        else:
            tenants = list(
                (
                    await db.execute(select(BoletoEvento.tenant_id).distinct())
                ).scalars().all()
            )
        print(f"tenants: {len(tenants)} | banco={banco or 'todos'}")
        for tid in tenants:
            res = await project_tenant_vigente(db, tenant_id=tid, banco=banco)
            print(f"  {tid}: {res}")


if __name__ == "__main__":
    asyncio.run(main())
