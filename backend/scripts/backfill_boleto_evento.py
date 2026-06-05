"""Backfill: decode bronze CNAB -> wh_boleto_evento (Fatia 2 do rebuild).

Reprocessa todo o bronze de retorno ja ingerido (`wh_cnab_raw_ocorrencia`) para
a timeline `wh_boleto_evento`. Idempotente (upsert por ocorrencia_id) -- pode
re-rodar a vontade; bumpar DECODER_VERSION + re-rodar reprocessa a taxonomia.

Uso (de backend/):
    .venv/bin/python scripts/backfill_boleto_evento.py                 # todos os tenants
    .venv/bin/python scripts/backfill_boleto_evento.py <tenant_id>     # um tenant
    .venv/bin/python scripts/backfill_boleto_evento.py <tenant_id> bradesco
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

from sqlalchemy import select

# Side-effect imports (registry SQLAlchemy completo).
import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.cobranca.decode_evento import (
    decode_tenant_eventos,
)
from app.warehouse.cnab_raw_arquivo import CnabRawArquivo


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
                    await db.execute(
                        select(CnabRawArquivo.tenant_id).distinct()
                    )
                ).scalars().all()
            )
        print(f"tenants: {len(tenants)} | banco={banco or 'todos'}")
        for tid in tenants:
            res = await decode_tenant_eventos(db, tenant_id=tid, banco=banco)
            print(f"  {tid}: {res}")


if __name__ == "__main__":
    asyncio.run(main())
