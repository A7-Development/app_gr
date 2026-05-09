"""Reprocessa wh_estoque_recebivel a partir de wh_qitech_raw_relatorio.

Use quando:
1. Schema do canonico mudou (ex.: precisao numerica ampliada — ALTER COLUMN)
   e queremos recarregar valores com fidelidade plena do raw.
2. Mapper mudou (regra de negocio nova) e queremos refletir em snapshots
   ja ingeridos.

Idempotente — upsert sobre `(tenant_id, source_id)`. Raw e imutavel,
silver e re-mapeavel por construcao (CLAUDE.md §13.2).

NAO toca em rede (nao bate na QiTech). NAO recriar `qitech_report_job` —
o job que originou cada raw continua intacto.

Uso (de backend/):
    # Reprocessa 1 data especifica
    .venv\\Scripts\\python.exe -m scripts.reprocess_fidc_estoque \\
        --tenant-slug a7-credit --data-posicao 2026-05-05

    # Reprocessa todos os snapshots fidc-estoque do tenant
    .venv\\Scripts\\python.exe -m scripts.reprocess_fidc_estoque \\
        --tenant-slug a7-credit --all
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from itertools import islice
from uuid import UUID

# Side-effect imports (registry SQLAlchemy completo).
import app.shared.identity.tenant  # noqa: F401
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.admin.qitech.etl import (
    CHUNK_SIZE,
    MAX_PG_PARAMS,
)
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_fidc_estoque,
)
from app.warehouse.estoque_recebivel import EstoqueRecebivel
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio


async def _resolve_tenant_id(slug: str) -> UUID:
    async with AsyncSessionLocal() as db:
        tid = await db.scalar(
            text("SELECT id FROM tenants WHERE slug = :s"), {"s": slug}
        )
        if not tid:
            raise RuntimeError(f"tenant slug='{slug}' nao encontrado")
        return tid


async def _list_raws(
    tenant_id: UUID, data_posicao: date | None
) -> list[QiTechRawRelatorio]:
    async with AsyncSessionLocal() as db:
        stmt = select(QiTechRawRelatorio).where(
            QiTechRawRelatorio.tenant_id == tenant_id,
            QiTechRawRelatorio.tipo_de_mercado == "fidc-estoque",
        )
        if data_posicao is not None:
            stmt = stmt.where(QiTechRawRelatorio.data_posicao == data_posicao)
        stmt = stmt.order_by(QiTechRawRelatorio.data_posicao.asc())
        return list((await db.execute(stmt)).scalars().all())


def _chunked(it, size):
    it = iter(it)
    while chunk := list(islice(it, size)):
        yield chunk


async def _reprocess_one(raw: QiTechRawRelatorio) -> int:
    """Re-mapeia um raw e faz upsert no canonico. Retorna linhas afetadas."""
    if not raw.payload_text:
        print(
            f"  [skip] raw {raw.id} ({raw.data_posicao}): payload_text vazio "
            f"(http_status={raw.http_status})"
        )
        return 0

    canonical_rows = map_fidc_estoque(
        csv_text=raw.payload_text,
        tenant_id=raw.tenant_id,
        data_referencia=raw.data_posicao,
    )
    if not canonical_rows:
        print(f"  [skip] raw {raw.id} ({raw.data_posicao}): mapper retornou 0 linhas")
        return 0

    all_columns = [
        c.name for c in EstoqueRecebivel.__table__.columns if c.name != "id"
    ]
    normalized = [{c: row.get(c) for c in all_columns} for row in canonical_rows]
    seen: dict[str, dict] = {}
    for r in normalized:
        seen[r["source_id"]] = r
    deduped = list(seen.values())

    chunk_size = max(1, min(CHUNK_SIZE, MAX_PG_PARAMS // len(all_columns)))
    update_cols = [
        c.name
        for c in EstoqueRecebivel.__table__.columns
        if c.name not in {"id", "tenant_id", "source_id", "ingested_at"}
    ]

    rows_upserted = 0
    async with AsyncSessionLocal() as db:
        for chunk in _chunked(deduped, chunk_size):
            stmt = pg_insert(EstoqueRecebivel.__table__).values(chunk)
            update_set = {name: stmt.excluded[name] for name in update_cols}
            stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id", "source_id"], set_=update_set
            )
            await db.execute(stmt)
            rows_upserted += len(chunk)
        await db.commit()
    return rows_upserted


async def _main_async(args: argparse.Namespace) -> int:
    tenant_id = await _resolve_tenant_id(args.tenant_slug)
    data_posicao: date | None = (
        date.fromisoformat(args.data_posicao) if args.data_posicao else None
    )
    raws = await _list_raws(tenant_id, data_posicao)
    if not raws:
        scope = (
            f"data_posicao={data_posicao.isoformat()}"
            if data_posicao
            else "TODOS os snapshots fidc-estoque"
        )
        print(f"[reprocess] nenhum raw encontrado pra tenant={args.tenant_slug} ({scope})")
        return 1

    print(
        f"[reprocess] tenant={args.tenant_slug} tenant_id={tenant_id} "
        f"raws_a_processar={len(raws)}"
    )
    total = 0
    for raw in raws:
        n = await _reprocess_one(raw)
        total += n
        print(f"  [ok] {raw.data_posicao}: {n} linhas upserted")
    print(f"[reprocess] DONE total_rows_upserted={total}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--tenant-slug", required=True, help="Slug do tenant (ex.: a7-credit)"
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--data-posicao",
        help="Data da posicao a reprocessar (ISO YYYY-MM-DD). Reprocessa apenas esse dia.",
    )
    g.add_argument(
        "--all",
        action="store_true",
        dest="reprocess_all",
        help="Reprocessa TODOS os snapshots fidc-estoque do tenant.",
    )
    args = p.parse_args()
    if args.reprocess_all:
        args.data_posicao = None
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
