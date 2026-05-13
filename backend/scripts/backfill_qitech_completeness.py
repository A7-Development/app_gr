"""Backfill `wh_qitech_raw_relatorio.completeness` — Opcao A, 2026-05-13.

Coluna `completeness` introduzida pela migration `e4a7b2c9d031`. Rows
ingeridas antes do upsert ja avaliar a completeness ficam com NULL — esse
script avalia em batch usando o mesmo inspector (`adapters/admin/qitech/
completeness.py`) que o pipeline novo usa em-runtime.

Pipeline:
    SELECT raw rows WHERE completeness IS NULL (com JOIN p/ pegar nome da UA)
      -> assess_completeness(tipo, payload, http_status, ua_nome)
      -> UPDATE em batch via VALUES + JOIN

Idempotente: o WHERE filtra rows ainda nao avaliadas; re-rodar nao mexe nas
ja preenchidas. Use --reassess pra reavaliar TUDO (util quando o inspector
ganha regra nova).

Uso (de backend/, com .venv ativo):
    .venv\\Scripts\\python.exe scripts/backfill_qitech_completeness.py
    .venv\\Scripts\\python.exe scripts/backfill_qitech_completeness.py --tenant <uuid>
    .venv\\Scripts\\python.exe scripts/backfill_qitech_completeness.py --tipo rf
    .venv\\Scripts\\python.exe scripts/backfill_qitech_completeness.py --reassess
    .venv\\Scripts\\python.exe scripts/backfill_qitech_completeness.py --dry-run

Args:
    --tenant <uuid>           limita a 1 tenant (default: todos os tenants)
    --tipo <str>              limita a 1 tipo_de_mercado (default: todos)
    --reassess                ignora o filtro `completeness IS NULL` (reavalia tudo)
    --batch <n>               linhas por batch (default 500)
    --dry-run                 imprime distribuicao mas nao escreve no banco
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from typing import Any
from uuid import UUID

from sqlalchemy import select, text, update

# Side-effect imports (registry SQLAlchemy completo).
import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.integracoes.adapters.admin.qitech.completeness import (
    assess_completeness,
)
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", type=str, default=None)
    parser.add_argument("--tipo", type=str, default=None)
    parser.add_argument("--reassess", action="store_true")
    parser.add_argument("--batch", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


async def _resolve_ua_nomes(
    tenant_ua_ids: set[tuple[UUID, UUID]],
) -> dict[tuple[UUID, UUID], str]:
    """Resolve `ua_nome` para um conjunto de (tenant, ua) — 1 query so."""
    if not tenant_ua_ids:
        return {}
    async with AsyncSessionLocal() as db:
        stmt = select(
            UnidadeAdministrativa.tenant_id,
            UnidadeAdministrativa.id,
            UnidadeAdministrativa.nome,
        ).where(
            UnidadeAdministrativa.id.in_({ua for _, ua in tenant_ua_ids}),
        )
        rows = (await db.execute(stmt)).all()
        return {(r[0], r[1]): r[2] for r in rows}


async def _fetch_batch(
    *,
    tenant_id: UUID | None,
    tipo: str | None,
    reassess: bool,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """Le um batch de rows raw. Quando reassess=False, so as NULL."""
    where = ["1=1"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if not reassess:
        where.append("completeness IS NULL")
    if tenant_id is not None:
        where.append("tenant_id = :tenant_id")
        params["tenant_id"] = tenant_id
    if tipo is not None:
        where.append("tipo_de_mercado = :tipo")
        params["tipo"] = tipo

    sql = text(
        f"""
        SELECT id, tenant_id, tipo_de_mercado, data_posicao, payload,
               http_status, unidade_administrativa_id, completeness
        FROM wh_qitech_raw_relatorio
        WHERE {" AND ".join(where)}
        ORDER BY id
        LIMIT :limit OFFSET :offset
        """
    )
    async with AsyncSessionLocal() as db:
        result = await db.execute(sql, params)
        return [dict(r._mapping) for r in result.all()]


async def _apply_batch(
    rows: list[dict[str, Any]],
    ua_nomes: dict[tuple[UUID, UUID], str],
    *,
    dry_run: bool,
) -> Counter[str]:
    """Avalia cada row + UPDATE em batch (1 UPDATE por row via primary key)."""
    counter: Counter[str] = Counter()
    if not rows:
        return counter

    async with AsyncSessionLocal() as db:
        for row in rows:
            ua_nome = ua_nomes.get(
                (row["tenant_id"], row["unidade_administrativa_id"])
            ) if row["unidade_administrativa_id"] is not None else None
            new_value = assess_completeness(
                tipo_de_mercado=row["tipo_de_mercado"],
                payload=row["payload"],
                http_status=row["http_status"],
                ua_nome=ua_nome,
            )
            label = new_value or "skip(no_ua)"
            counter[label] += 1
            if dry_run or new_value is None:
                continue
            await db.execute(
                update(QiTechRawRelatorio)
                .where(QiTechRawRelatorio.id == row["id"])
                .values(completeness=new_value)
            )
        if not dry_run:
            await db.commit()
    return counter


async def main() -> int:
    args = _parse_args()
    tenant_id = UUID(args.tenant) if args.tenant else None

    total = Counter[str]()
    offset = 0
    processed = 0

    while True:
        rows = await _fetch_batch(
            tenant_id=tenant_id,
            tipo=args.tipo,
            reassess=args.reassess,
            limit=args.batch,
            offset=offset,
        )
        if not rows:
            break

        tenant_ua_ids = {
            (r["tenant_id"], r["unidade_administrativa_id"])
            for r in rows
            if r["unidade_administrativa_id"] is not None
        }
        ua_nomes = await _resolve_ua_nomes(tenant_ua_ids)
        batch_counter = await _apply_batch(rows, ua_nomes, dry_run=args.dry_run)
        total.update(batch_counter)

        processed += len(rows)
        print(
            f"[batch] offset={offset:>7} rows={len(rows):>4} "
            f"complete={batch_counter.get('complete', 0):>4} "
            f"partial={batch_counter.get('partial', 0):>4} "
            f"empty={batch_counter.get('empty', 0):>4} "
            f"skip={batch_counter.get('skip(no_ua)', 0):>4}",
            flush=True,
        )

        # Quando reassess=False, rows com NULL viram nao-NULL apos UPDATE.
        # Mantemos offset em 0 — proxima query vai ler outras rows NULL.
        # Quando reassess=True ou dry_run=True, paginamos com offset.
        if args.reassess or args.dry_run:
            offset += args.batch
        # else: offset fica em 0 — fetch volta as proximas NULL.

    print()
    print(f"Total processado: {processed}")
    print(f"  complete : {total.get('complete', 0)}")
    print(f"  partial  : {total.get('partial', 0)}")
    print(f"  empty    : {total.get('empty', 0)}")
    print(f"  sem UA   : {total.get('skip(no_ua)', 0)}")
    if args.dry_run:
        print("(dry-run — nenhuma row foi atualizada)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
