"""Replay raw -> silver do fidc-estoque para datas presas no limbo.

Contexto (2026-06-12): bug do `numeric field overflow` (taxaRecebivel
absurda da QiTech estourava NUMERIC(14,10)) abortava o upsert da silver
DEPOIS da raw commitada — datas ficavam com raw integra e silver vazia,
e o qitech_report_job em "SUCCESS sem completed_at". Fix estrutural no
PR #320 (colunas NUMERIC(24,10) + callback marca ERROR). Este script
reprocessa as datas presas direto da raw, sem nova chamada a QiTech.

Replay autorizado pela §13.2.1 (scripts de auditoria/replay leem raw).
Logica de mapper+upsert identica a `process_fidc_estoque_callback`.

Idempotente: upsert por business key — rodar 2x nao duplica.

Uso (na VM26):
    sudo -u app_gr .venv/bin/python scripts/remap_fidc_estoque_from_raw.py \
        --dates 2025-12-18,2025-12-19,2026-04-09 [--dry-run]

    --dates    Lista de data_posicao (YYYY-MM-DD) separadas por virgula.
               Default: todas as datas com raw nao-vazia e silver zerada.
    --dry-run  So mostra o plano (datas, linhas mapeadas), sem gravar.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime
from itertools import islice
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import app.shared.identity  # noqa: F401,E402 — carrega Tenant pra resolver FKs
import app.warehouse  # noqa: F401,E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.modules.integracoes.adapters.admin.qitech.etl import (  # noqa: E402
    CHUNK_SIZE,
    MAX_PG_PARAMS,
)
from app.modules.integracoes.adapters.admin.qitech.mappers import (  # noqa: E402
    map_fidc_estoque,
)
from app.warehouse.estoque_recebivel import EstoqueRecebivel  # noqa: E402
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio  # noqa: E402

_FIND_STUCK_SQL = text(
    """
    SELECT r.data_posicao
    FROM wh_qitech_raw_relatorio r
    WHERE r.tipo_de_mercado = 'fidc-estoque'
      AND length(r.payload_text) > 0
      AND NOT EXISTS (
        SELECT 1 FROM wh_estoque_recebivel e
        WHERE e.data_referencia = r.data_posicao
      )
    ORDER BY r.data_posicao
    """
)

_FIX_JOB_SQL = text(
    """
    UPDATE qitech_report_job
    SET completed_at = :now,
        result_downloaded_at = COALESCE(result_downloaded_at, :now),
        raw_relatorio_id = :raw_id,
        error_message = NULL
    WHERE report_type = 'fidc-estoque'
      AND reference_date = :ref
      AND status = 'SUCCESS'
      AND completed_at IS NULL
    """
)


async def _remap_date(db, target: date, *, dry_run: bool) -> int:
    raw = (
        await db.execute(
            select(QiTechRawRelatorio)
            .where(
                QiTechRawRelatorio.tipo_de_mercado == "fidc-estoque",
                QiTechRawRelatorio.data_posicao == target,
            )
            .order_by(QiTechRawRelatorio.fetched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if raw is None or not raw.payload_text:
        print(f"  {target}: SEM raw nao-vazia — pulando")
        return 0

    canonical_rows = map_fidc_estoque(
        csv_text=raw.payload_text,
        tenant_id=raw.tenant_id,
        data_referencia=target,
    )
    if dry_run:
        print(f"  {target}: {len(canonical_rows)} linhas mapeadas (dry-run)")
        return 0

    # Upsert identico ao process_fidc_estoque_callback (business key).
    bk_cols = [
        "tenant_id", "data_referencia", "fundo_doc", "cedente_doc",
        "seu_numero", "numero_documento",
    ]
    all_columns = [
        c.name for c in EstoqueRecebivel.__table__.columns if c.name != "id"
    ]
    normalized = [{c: row.get(c) for c in all_columns} for row in canonical_rows]
    seen: dict[tuple, dict] = {}
    for r in normalized:
        seen[tuple(r[c] for c in bk_cols)] = r
    deduped = list(seen.values())

    chunk_size = max(1, min(CHUNK_SIZE, MAX_PG_PARAMS // len(all_columns)))
    update_cols = [
        c.name
        for c in EstoqueRecebivel.__table__.columns
        if c.name not in {"id", *bk_cols, "ingested_at"}
    ]

    def _chunked(it, size):
        it = iter(it)
        while chunk := list(islice(it, size)):
            yield chunk

    rows_inserted = 0
    for chunk in _chunked(deduped, chunk_size):
        stmt = pg_insert(EstoqueRecebivel.__table__).values(chunk)
        update_set = {name: stmt.excluded[name] for name in update_cols}
        stmt = stmt.on_conflict_do_update(index_elements=bk_cols, set_=update_set)
        await db.execute(stmt)
        rows_inserted += len(chunk)

    # Tira o job do limbo (SUCCESS sem completed_at).
    await db.execute(
        _FIX_JOB_SQL,
        {"now": datetime.now(UTC), "ref": target, "raw_id": raw.id},
    )
    await db.commit()
    print(f"  {target}: {rows_inserted} linhas upsertadas na silver")
    return rows_inserted


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        if args.dates:
            targets = [
                date.fromisoformat(s.strip()) for s in args.dates.split(",")
            ]
        else:
            targets = [
                row[0] for row in (await db.execute(_FIND_STUCK_SQL)).all()
            ]

        if not targets:
            print("Nenhuma data presa (raw nao-vazia + silver zerada).")
            return

        print(f"Datas a reprocessar: {', '.join(str(t) for t in targets)}")
        total = 0
        for target in targets:
            total += await _remap_date(db, target, dry_run=args.dry_run)
        print(f"Total: {total} linhas")


if __name__ == "__main__":
    asyncio.run(main())
