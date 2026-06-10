"""(Re)constroi lab_serasa_pj_liminar_feature a partir do silver.

Uso (do diretorio backend/):

    .venv\\Scripts\\python.exe scripts/serasa_liminar_features_build.py

Roda para TODOS os tenants com consultas Serasa PJ. Idempotente (UPSERT
por tenant_id+raw_id); `label_liminar` curado sobrevive a re-extracao.

Labels: preencher por fora via `bitfin_consulta_id` (flag Liminar do
dbo.ConsultaFinanceira) — ex. via MCP/SQL apos o build:

    UPDATE lab_serasa_pj_liminar_feature f
    SET label_liminar = <true|false>
    FROM wh_serasa_pj_raw_relatorio r
    WHERE r.id = f.raw_id AND r.bitfin_consulta_id IN (...);
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import distinct, select

import app.shared.identity.tenant
import app.warehouse  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.modules.laboratorio.services.serasa_liminar_features import (
    EXTRACTOR_VERSION,
    build_features,
)
from app.warehouse.serasa_pj_consulta import SerasaPjConsulta


async def main() -> int:
    async with AsyncSessionLocal() as db:
        tenant_ids = list(
            (
                await db.execute(
                    select(distinct(SerasaPjConsulta.tenant_id))
                )
            ).scalars()
        )

    print(
        f"[features] extractor={EXTRACTOR_VERSION} · "
        f"{len(tenant_ids)} tenant(s)"
    )
    total = 0
    for tid in tenant_ids:
        async with AsyncSessionLocal() as db:
            n = await build_features(db, tenant_id=tid)
            await db.commit()
        print(f"[features] tenant={tid}: {n} linhas upsertadas")
        total += n

    print(f"[features] total: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
