"""Seed inicial de `wh_dim_dia_util`.

Le feriados nacionais de `Bitfin.VW_FERIADOS_NACIONAL`, gera todas as datas
do range pedido (default 2019-01-01 a 2030-12-31), calcula flags + indices
precomputados e faz upsert em `wh_dim_dia_util`.

Uso (a partir da raiz do backend, com .venv ativo):

    python -m scripts.populate_dia_util --tenant a7-credit
    python -m scripts.populate_dia_util --tenant a7-credit --start-year 2019 --end-year 2030

Idempotente: re-rodar nao duplica linhas (upsert por `(tenant_id, data)`).

Segue o pattern de `app/modules/integracoes/adapters/erp/bitfin/bootstrap.py`:
- Resolve tenant pelo slug (string-friendly).
- Le credencial cifrada de `tenant_source_config` via `get_decrypted_config`.
- Abre conexao MSSQL via `BitfinConfig.from_dict`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import SourceType
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.modules.integracoes.adapters.erp.bitfin.connection import fetch_rows
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    list_configs,
)
from app.core.enums import SourceType
from app.shared.identity.tenant import Tenant
from app.warehouse.dim_dia_util import DimDiaUtil

ADAPTER_VERSION = "dim_dia_util_seed_v1.0.0"

DOW_NAMES_PT = {
    1: "Segunda",
    2: "Terça",
    3: "Quarta",
    4: "Quinta",
    5: "Sexta",
    6: "Sábado",
    7: "Domingo",
}

logger = logging.getLogger("populate_dia_util")


async def _resolve_tenant_id(slug: str) -> UUID:
    async with AsyncSessionLocal() as db:
        stmt = select(Tenant).where(Tenant.slug == slug)
        tenant = (await db.execute(stmt)).scalar_one_or_none()
        if tenant is None:
            raise SystemExit(f"Tenant com slug '{slug}' nao encontrado.")
        return tenant.id


async def _load_bitfin_config(tenant_id: UUID) -> BitfinConfig:
    """Le qualquer linha enabled de erp:bitfin do tenant.

    Pos-Phase-F multi-UA, credencial Bitfin pode estar vinculada a uma UA
    especifica. Para o seed de feriados (que e tenant-scoped, nao UA-scoped),
    qualquer credencial enabled serve — feriados nacionais sao iguais para
    qualquer UA do tenant.
    """
    async with AsyncSessionLocal() as db:
        rows = await list_configs(db, tenant_id, SourceType.ERP_BITFIN)
        enabled_row = next((r for r in rows if r.enabled), None)
        if enabled_row is None:
            raise SystemExit(
                f"Tenant {tenant_id} nao tem tenant_source_config enabled para erp:bitfin."
            )
        cfg_dict = decrypt_config(enabled_row.config)
    return BitfinConfig.from_dict(cfg_dict)


def _fetch_feriados_nacionais(
    config: BitfinConfig, database: str, start: date, end: date
) -> set[date]:
    """SELECT em VW_FERIADOS_NACIONAL filtrando pelo range de anos."""
    sql = (
        "SELECT Dia, Mes, Ano FROM VW_FERIADOS_NACIONAL "
        "WHERE Ano BETWEEN ? AND ?"
    )
    rows = fetch_rows(config, database, sql, (start.year, end.year))
    out: set[date] = set()
    for r in rows:
        try:
            d = date(int(r["Ano"]), int(r["Mes"]), int(r["Dia"]))
        except (ValueError, TypeError):
            continue
        if start <= d <= end:
            out.add(d)
    return out


def _build_rows(
    tenant_id: UUID,
    start: date,
    end: date,
    feriados: set[date],
) -> list[dict]:
    """Gera 1 linha por dia com flags + indices precomputados."""
    # Indexar dias uteis por mes para `dia_util_index_no_mes` e
    # `total_dias_uteis_no_mes`.
    dus_por_mes: dict[tuple[int, int], list[date]] = {}
    cursor = start
    while cursor <= end:
        dow = cursor.isoweekday()
        eh_fds = dow >= 6
        eh_feriado = cursor in feriados
        if (not eh_fds) and (not eh_feriado):
            dus_por_mes.setdefault((cursor.year, cursor.month), []).append(cursor)
        cursor += timedelta(days=1)

    rows: list[dict] = []
    cursor = start
    while cursor <= end:
        dow = cursor.isoweekday()
        eh_fds = dow >= 6
        eh_feriado = cursor in feriados
        eh_du = (not eh_fds) and (not eh_feriado)
        chave = (cursor.year, cursor.month)
        dus_mes = dus_por_mes.get(chave, [])
        total_du_mes = len(dus_mes)
        du_idx = (dus_mes.index(cursor) + 1) if eh_du else None
        # Semana do mes 1..5 = ceil(day / 7)
        semana = (cursor.day + 6) // 7
        rows.append(
            {
                "tenant_id": tenant_id,
                "data": cursor,
                "dia_da_semana": dow,
                "dia_da_semana_nome": DOW_NAMES_PT.get(dow, "(n/d)"),
                "eh_fim_de_semana": eh_fds,
                "eh_feriado_nacional": eh_feriado,
                "eh_dia_util": eh_du,
                "dia_util_index_no_mes": du_idx,
                "total_dias_uteis_no_mes": total_du_mes,
                "semana_do_mes": semana,
                "source_type": "DERIVED",
                "ingested_by_version": ADAPTER_VERSION,
            }
        )
        cursor += timedelta(days=1)
    return rows


async def _upsert(db: AsyncSession, rows: list[dict]) -> int:
    """Bulk upsert por (tenant_id, data). Em chunks para nao estourar limite de params."""
    if not rows:
        return 0
    CHUNK = 500
    total = 0
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        stmt = pg_insert(DimDiaUtil.__table__).values(chunk)
        update_cols = {
            "dia_da_semana": stmt.excluded.dia_da_semana,
            "dia_da_semana_nome": stmt.excluded.dia_da_semana_nome,
            "eh_fim_de_semana": stmt.excluded.eh_fim_de_semana,
            "eh_feriado_nacional": stmt.excluded.eh_feriado_nacional,
            "eh_dia_util": stmt.excluded.eh_dia_util,
            "dia_util_index_no_mes": stmt.excluded.dia_util_index_no_mes,
            "total_dias_uteis_no_mes": stmt.excluded.total_dias_uteis_no_mes,
            "semana_do_mes": stmt.excluded.semana_do_mes,
            "ingested_by_version": stmt.excluded.ingested_by_version,
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_wh_dim_dia_util", set_=update_cols
        )
        await db.execute(stmt)
        total += len(chunk)
    await db.commit()
    return total


async def _main(args: argparse.Namespace) -> None:
    tenant_id = await _resolve_tenant_id(args.tenant)
    cfg = await _load_bitfin_config(tenant_id)

    start = date(args.start_year, 1, 1)
    end = date(args.end_year, 12, 31)

    logger.info(
        "Tenant=%s (%s) — feriados em %s.%s",
        args.tenant, tenant_id, cfg.server, cfg.database_bitfin,
    )
    feriados = _fetch_feriados_nacionais(cfg, cfg.database_bitfin, start, end)
    logger.info("Feriados encontrados: %d", len(feriados))

    rows = _build_rows(tenant_id, start, end, feriados)
    logger.info("Linhas a upsert: %d", len(rows))

    async with AsyncSessionLocal() as db:
        n = await _upsert(db, rows)
    logger.info("Upsert concluido: %d linhas processadas.", n)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Seed inicial de wh_dim_dia_util")
    parser.add_argument("--tenant", default="a7-credit", help="Slug do tenant (default: a7-credit)")
    parser.add_argument("--start-year", type=int, default=2019)
    parser.add_argument("--end-year", type=int, default=2030)
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
