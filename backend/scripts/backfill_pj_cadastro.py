"""Backfill: wh_bdc_raw_consulta -> wh_pj_cadastro (silver canônico).

Re-mapeia o último payload BDC `found=true` de cada (tenant, cnpj) para o silver
canônico `wh_pj_cadastro`. Idempotente (upsert por tenant+cnpj). Rodar na VM26:

    cd /opt/app_gr/backend && python -m scripts.backfill_pj_cadastro

Heads alembic divergentes -> não é migration; é runner pontual (CLAUDE.md §13.2.1
permite leitura ad-hoc do raw em scripts/).
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.data.bigdatacorp.mappers.cadastral import (
    map_basic_data,
)
from app.modules.integracoes.adapters.data.bigdatacorp.version import (
    ADAPTER_VERSION,
)
from app.modules.integracoes.services.pj_cadastro_silver import upsert_pj_cadastro

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gr.backfill.pj_cadastro")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT DISTINCT ON (tenant_id, cnpj)
                        id, tenant_id, cnpj, datasets, payload, payload_sha256
                    FROM wh_bdc_raw_consulta
                    WHERE public_code = 'CAD-PJ' AND found = true
                    ORDER BY tenant_id, cnpj, fetched_at DESC
                    """
                )
            )
        ).all()

    logger.info("Backfill wh_pj_cadastro: %d (tenant,cnpj) candidatos", len(rows))
    ok = 0
    skip = 0
    for raw_id, tenant_id, cnpj, datasets, payload, sha in rows:
        mapped = map_basic_data(payload, dataset=datasets or "basic_data")
        if not mapped.found or mapped.fields is None:
            skip += 1
            continue
        async with AsyncSessionLocal() as db:
            await upsert_pj_cadastro(
                db,
                tenant_id=tenant_id,
                cnpj=cnpj,
                fields=mapped.fields,
                raw_id=raw_id,
                hash_origem=sha,
                ingested_by_version=ADAPTER_VERSION,
            )
            await db.commit()
        ok += 1

    logger.info("Backfill concluído: %d upserts, %d pulados (sem dados)", ok, skip)


if __name__ == "__main__":
    asyncio.run(main())
