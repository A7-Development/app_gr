"""Ingere acervo historico do fidc-estoque (Portal FIDC) no warehouse.

Entrada: zip gerado por prepara_acervo.py (workstation) com 1 CSV por data
JA NORMALIZADO para o layout canonico da API QiTech (30 colunas camelCase)
+ staging_manifest.csv. Aqui:

  1. Para cada data: se ja existe raw NAO-VAZIA vinda da API, PULA
     (API e fonte primaria; acervo so preenche o que ela nao tem).
  2. Senao: upsert em wh_qitech_raw_relatorio com
     fetched_by_version='portal_fidc_archive_v1.0.0' e meta do arquivo
     de origem (proveniencia distinta da API).
  3. Mapper canonico map_fidc_estoque (reuso integral) -> override de
     proveniencia (trust_level=MEDIUM, ingested_by_version=archive) ->
     upsert em wh_estoque_recebivel.

Idempotente: re-rodar substitui apenas linhas archive (API sempre vence).

Uso (na VM26, de /opt/app_gr/backend):
    sudo -u app_gr env PYTHONPATH=/opt/app_gr/backend .venv/bin/python \
        /tmp/ingest_fidc_estoque_archive.py --zip /tmp/acervo_staging.zip \
        [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import zipfile
from datetime import UTC, date, datetime
from itertools import islice
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import app.shared.identity  # noqa: F401,E402
import app.warehouse  # noqa: F401,E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.enums import TrustLevel  # noqa: E402
from app.modules.integracoes.adapters.admin.qitech.etl import (  # noqa: E402
    CHUNK_SIZE,
    MAX_PG_PARAMS,
)
from app.modules.integracoes.adapters.admin.qitech.hashing import (  # noqa: E402
    sha256_of_row,
)
from app.modules.integracoes.adapters.admin.qitech.mappers import (  # noqa: E402
    map_fidc_estoque,
)
from app.warehouse.estoque_recebivel import EstoqueRecebivel  # noqa: E402
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio  # noqa: E402

ARCHIVE_VERSION = "portal_fidc_archive_v1.0.0"
UA_REALINVEST = "6170ce55-b566-42ba-a3e7-5ea8dde56b64"

_EXISTING_RAW_SQL = text(
    """
    SELECT id, fetched_by_version, coalesce(length(payload_text), 0) AS bytes
    FROM wh_qitech_raw_relatorio
    WHERE tenant_id = :tenant AND tipo_de_mercado = 'fidc-estoque'
      AND data_posicao = :d
      AND unidade_administrativa_id = :ua
    """
)
_TENANT_SQL = text("SELECT id FROM tenants WHERE slug = :slug")


async def _upsert_silver(db, rows):
    bk_cols = [
        "tenant_id", "data_referencia", "fundo_doc", "cedente_doc",
        "seu_numero", "numero_documento",
    ]
    all_columns = [
        c.name for c in EstoqueRecebivel.__table__.columns if c.name != "id"
    ]
    normalized = [{c: r.get(c) for c in all_columns} for r in rows]
    seen: dict[tuple, dict] = {}
    for r in normalized:
        seen[tuple(r[c] for c in bk_cols)] = r
    deduped = list(seen.values())
    chunk_size = max(1, min(CHUNK_SIZE, MAX_PG_PARAMS // len(all_columns)))
    update_cols = [
        c.name for c in EstoqueRecebivel.__table__.columns
        if c.name not in {"id", *bk_cols, "ingested_at"}
    ]

    def _chunked(it, size):
        it = iter(it)
        while chunk := list(islice(it, size)):
            yield chunk

    n = 0
    for chunk in _chunked(deduped, chunk_size):
        stmt = pg_insert(EstoqueRecebivel.__table__).values(chunk)
        update_set = {name: stmt.excluded[name] for name in update_cols}
        stmt = stmt.on_conflict_do_update(index_elements=bk_cols, set_=update_set)
        await db.execute(stmt)
        n += len(chunk)
    return n


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--tenant-slug", default="a7-credit")
    parser.add_argument("--ua", default=UA_REALINVEST)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    z = zipfile.ZipFile(args.zip)
    datas = sorted(
        n[:-4] for n in z.namelist() if n.endswith(".csv") and n[0].isdigit()
    )
    if args.limit:
        datas = datas[: args.limit]
    print(f"zip: {len(datas)} datas candidatas")

    async with AsyncSessionLocal() as db:
        tenant_id = (
            await db.execute(_TENANT_SQL, {"slug": args.tenant_slug})
        ).scalar_one()

        ingeridas, puladas_api, linhas_total = 0, 0, 0
        for i, d_str in enumerate(datas, 1):
            target = date.fromisoformat(d_str)
            existing = (
                await db.execute(
                    _EXISTING_RAW_SQL,
                    {"tenant": tenant_id, "d": target, "ua": args.ua},
                )
            ).first()
            if (
                existing is not None
                and existing.bytes > 0
                and not str(existing.fetched_by_version).startswith("portal_fidc")
            ):
                puladas_api += 1
                continue

            csv_text = z.read(f"{d_str}.csv").decode("utf-8")
            if args.dry_run:
                ingeridas += 1
                continue

            fetched_at = datetime.now(UTC)
            raw_dict = {
                "tenant_id": tenant_id,
                "unidade_administrativa_id": args.ua,
                "tipo_de_mercado": "fidc-estoque",
                "data_posicao": target,
                "payload": {
                    "format": "csv",
                    "delimiter": ";",
                    "source": "portal_fidc_archive",
                    "note": (
                        "snapshot baixado manualmente do Portal FIDC e "
                        "normalizado para o layout da API; http_status "
                        "sintetico; sem nomeGestor/docGestor/prazoAnual"
                    ),
                    "rows_estimate": csv_text.count("\n"),
                    "bytes": len(csv_text.encode("utf-8")),
                },
                "payload_text": csv_text,
                "http_status": 200,
                "payload_sha256": sha256_of_row({"csv": csv_text}),
                "fetched_at": fetched_at,
                "fetched_by_version": ARCHIVE_VERSION,
            }
            stmt = pg_insert(QiTechRawRelatorio.__table__).values(raw_dict)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_wh_qitech_raw_relatorio",
                set_={
                    "payload": stmt.excluded.payload,
                    "payload_text": stmt.excluded.payload_text,
                    "payload_sha256": stmt.excluded.payload_sha256,
                    "http_status": stmt.excluded.http_status,
                    "fetched_at": stmt.excluded.fetched_at,
                    "fetched_by_version": stmt.excluded.fetched_by_version,
                },
            )
            await db.execute(stmt)

            rows = map_fidc_estoque(
                csv_text=csv_text, tenant_id=tenant_id, data_referencia=target
            )
            for r in rows:
                r["trust_level"] = TrustLevel.MEDIUM
                r["ingested_by_version"] = ARCHIVE_VERSION
            n = await _upsert_silver(db, rows)
            await db.commit()
            ingeridas += 1
            linhas_total += n
            if i % 25 == 0:
                print(f"  [{i}/{len(datas)}] ate {d_str} | ingeridas={ingeridas} "
                      f"puladas_api={puladas_api} linhas={linhas_total}", flush=True)

        print(
            f"FIM: ingeridas={ingeridas} puladas_api={puladas_api} "
            f"linhas_silver={linhas_total} dry_run={args.dry_run}"
        )


if __name__ == "__main__":
    asyncio.run(main())
