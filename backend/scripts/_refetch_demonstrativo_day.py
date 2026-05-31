"""Re-fetch ao vivo do demonstrativo-caixa de 1 dia (REALINVEST).

Cirurgico: chama `sync_demonstrativo_caixa` (caminho ETL ao vivo, ja roteado
pra replace-by-partition). Usado pra recuperar dias orfaos sem raw, manter a
janela recente fresca (relatorios crescem por floating/postagem retroativa)
e validar o pipeline live end-to-end.

Uso:
    python -m scripts._refetch_demonstrativo_day 2024-07-31              # 1 dia
    python -m scripts._refetch_demonstrativo_day 2026-05-12 2026-05-29   # range
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import text

import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.etl import sync_demonstrativo_caixa
from app.modules.integracoes.services.source_config import decrypt_config, get_config

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


async def main() -> None:
    start = date.fromisoformat(sys.argv[1])
    end = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else start
    async with AsyncSessionLocal() as db:
        tenant_id: UUID = await db.scalar(
            text("SELECT id FROM tenants WHERE slug = 'a7-credit'")
        )
        ua_id: UUID = await db.scalar(
            text(
                "SELECT id FROM cadastros_unidade_administrativa "
                "WHERE cnpj = '42449234000160' AND tenant_id = :t"
            ),
            {"t": tenant_id},
        )
        cfg_row = await get_config(
            db, tenant_id, SourceType.ADMIN_QITECH, Environment.PRODUCTION,
            unidade_administrativa_id=ua_id,
        )
        config = QiTechConfig.from_dict(decrypt_config(cfg_row.config))

    d = start
    while d <= end:
        step = await sync_demonstrativo_caixa(
            tenant_id=tenant_id,
            environment=Environment.PRODUCTION,
            config=config,
            data_posicao=d,
            unidade_administrativa_id=ua_id,
        )
        print(
            f"[{d}] ok={step['ok']} http={step.get('raw_http_status')} "
            f"completeness={step.get('raw_completeness')} "
            f"mode={step.get('canonical_mode')} "
            f"rows={step.get('canonical_rows_upserted')} "
            f"orphans={step.get('canonical_orphans_removed')}"
        )
        if step.get("errors"):
            print("  errors:", step["errors"])
        d += timedelta(days=1)


if __name__ == "__main__":
    asyncio.run(main())
