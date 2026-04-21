"""CLI: ingere todo o historico do Bitfin/ANALYTICS para o tenant informado.

Uso:
    uv run python -m app.modules.integracoes.adapters.erp.bitfin.bootstrap
    uv run python -m app.modules.integracoes.adapters.erp.bitfin.bootstrap --tenant a7-credit
"""

from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.erp.bitfin.etl import sync_all
from app.shared.identity.tenant import Tenant


async def _resolve_tenant_id(slug: str) -> UUID:
    async with AsyncSessionLocal() as db:
        stmt = select(Tenant).where(Tenant.slug == slug)
        tenant = (await db.execute(stmt)).scalar_one_or_none()
        if tenant is None:
            raise SystemExit(f"Tenant com slug '{slug}' nao encontrado.")
        return tenant.id


async def _main(tenant_slug: str) -> None:
    tenant_id = await _resolve_tenant_id(tenant_slug)
    print(f"[bootstrap] tenant={tenant_slug} ({tenant_id})")
    summary = await sync_all(tenant_id, since=None)
    print(json.dumps(summary, default=str, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap do warehouse do GR")
    parser.add_argument(
        "--tenant", default="a7-credit", help="Slug do tenant alvo (default: a7-credit)"
    )
    args = parser.parse_args()
    asyncio.run(_main(args.tenant))


if __name__ == "__main__":
    main()
