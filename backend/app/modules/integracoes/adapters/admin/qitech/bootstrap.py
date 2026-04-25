"""CLI: testa auth QiTech para um tenant.

Uso:
    uv run python -m app.modules.integracoes.adapters.admin.qitech.bootstrap
    uv run python -m app.modules.integracoes.adapters.admin.qitech.bootstrap --tenant a7-credit
"""

from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.adapter import adapter_ping
from app.modules.integracoes.services.source_config import get_decrypted_config
from app.shared.identity.tenant import Tenant


async def _resolve_tenant_id(slug: str) -> UUID:
    async with AsyncSessionLocal() as db:
        stmt = select(Tenant).where(Tenant.slug == slug)
        tenant = (await db.execute(stmt)).scalar_one_or_none()
        if tenant is None:
            raise SystemExit(f"Tenant com slug '{slug}' nao encontrado.")
        return tenant.id


async def _main(tenant_slug: str, environment: Environment) -> None:
    tenant_id = await _resolve_tenant_id(tenant_slug)
    async with AsyncSessionLocal() as db:
        cfg = await get_decrypted_config(
            db, tenant_id, SourceType.ADMIN_QITECH, environment
        )
    if cfg is None:
        raise SystemExit(
            f"Tenant {tenant_id} sem tenant_source_config para admin:qitech "
            f"({environment.value})."
        )

    print(f"[bootstrap] tenant={tenant_slug} ({tenant_id}) env={environment.value}")
    result = await adapter_ping(
        cfg, tenant_id=tenant_id, environment=environment
    )
    print(json.dumps(result, default=str, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="QiTech adapter bootstrap/ping")
    parser.add_argument(
        "--tenant", default="a7-credit", help="Slug do tenant alvo (default: a7-credit)"
    )
    parser.add_argument(
        "--environment",
        choices=[Environment.SANDBOX.value, Environment.PRODUCTION.value],
        default=Environment.PRODUCTION.value,
    )
    args = parser.parse_args()
    asyncio.run(_main(args.tenant, Environment(args.environment)))


if __name__ == "__main__":
    main()
