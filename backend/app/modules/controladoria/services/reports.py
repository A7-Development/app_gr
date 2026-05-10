"""Controladoria · Relatorios — service layer.

Reads the catalog from `integracoes.public` and queries silver canonical
tables generically using table reflection (CLAUDE.md §13.2.1 — silver-only).

Why generic SQL via SQLAlchemy `Table` reflection instead of one repository
per slug:
    - 17 reports today, ~30+ when Kanastra arrives. A repository per slug
      would mean dozens of near-identical files.
    - Canonical tables share a uniform shape (Auditable mixin → tenant_id +
      proveniencia + a date column + an entity column). Generic dispatch
      from a `ReportSpec` covers all of them with a single function.
    - The frontend defines TS-types per slug; backend just returns rows as
      `dict[str, Any]`. Type safety lives in the contract (spec + TS-types),
      not in 17 Pydantic models.

Filtering by fundo:
    - Most QiTech reports have `unidade_administrativa_id` (UUID — internal
      identifier of the FIDC). For these, the API param `?fundo_id=<uuid>`
      maps directly to the column.
    - Async reports (`fidc_estoque`, `liquidados_baixados`, ...) use
      `fundo_doc` (CNPJ string) instead. For these, the API translates
      `fundo_id` → `cnpj_fundo` via the tenant's UAs (TODO — Phase 1.5;
      for now, these reports require `?fundo_doc` directly to be passed via
      a different param, OR the filter is silently ignored).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import MetaData, Table, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.public import get_report_spec, list_reports
from app.modules.integracoes.report_catalog import (
    ReportCategory,
    ReportSpec,
)

# Cache reflected tables across requests — reflection on first hit only,
# subsequent hits serve from memory.
_TABLE_CACHE: dict[str, Table] = {}


async def get_visible_reports(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    category: ReportCategory | None = None,
) -> list[ReportSpec]:
    """Return reports visible to the tenant, optionally filtered by category."""
    return await list_reports(db, tenant_id=tenant_id, category=category)


async def _reflect(db: AsyncSession, table_name: str) -> Table:
    """Reflect a silver table by name, caching the metadata.

    Reflection runs against the bound engine of the active session — this
    works for both prod and test fixtures (each has its own engine).
    """
    if table_name in _TABLE_CACHE:
        return _TABLE_CACHE[table_name]

    metadata = MetaData()
    bind = db.get_bind()

    def _reflect_sync(sync_conn: Any) -> Table:
        return Table(table_name, metadata, autoload_with=sync_conn)

    async with bind.connect() as conn:
        table = await conn.run_sync(_reflect_sync)

    _TABLE_CACHE[table_name] = table
    return table


async def query_report_rows(
    db: AsyncSession,
    *,
    spec: ReportSpec,
    tenant_id: UUID,
    fundo_id: UUID | None = None,
    periodo_inicio: date | None = None,
    periodo_fim: date | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Return paginated rows for a report + total count.

    Tenant-scoped (§10). Date filtering applied only when `spec.date_column`
    is set. Fund filtering applied only when `spec.fund_column` is set AND
    the column is a UUID type (i.e., `unidade_administrativa_id`). For
    `fundo_doc` (CNPJ) columns, fund_id translation is not yet implemented
    in Phase 1 and the filter is silently dropped.
    """
    table = await _reflect(db, spec.canonical_table)

    # Always tenant-scoped. Fail loudly if the table somehow does not have
    # tenant_id — no silent broad scan.
    tenant_col = table.c.get("tenant_id")
    if tenant_col is None:
        raise ValueError(
            f"canonical table {spec.canonical_table!r} has no tenant_id column — "
            f"refusing to query (multi-tenant invariant)"
        )

    where_clauses: list[Any] = [tenant_col == tenant_id]

    # Fund filter — only applied when spec declares it AND the column type
    # accepts the param shape.
    if spec.fund_column is not None and fundo_id is not None:
        fund_col = table.c.get(spec.fund_column)
        if fund_col is not None and spec.fund_column == "unidade_administrativa_id":
            where_clauses.append(fund_col == fundo_id)
        # fundo_doc translation is Phase 1.5 — silently skipped for now.

    # Date filters.
    if spec.date_column is not None:
        date_col = table.c.get(spec.date_column)
        if date_col is not None:
            if periodo_inicio is not None:
                where_clauses.append(date_col >= periodo_inicio)
            if periodo_fim is not None:
                where_clauses.append(date_col <= periodo_fim)

    where = and_(*where_clauses)

    # Total count (separate query; the rows query may be ordered differently).
    count_stmt = select(func.count()).select_from(table).where(where)
    total = (await db.execute(count_stmt)).scalar_one()

    # Rows. Order by ingested_at DESC when available, else by date column DESC,
    # else by primary key ASC. Stable ordering matters for pagination.
    order_by = []
    if "ingested_at" in table.c:
        order_by.append(table.c.ingested_at.desc())
    elif spec.date_column and spec.date_column in table.c:
        order_by.append(table.c[spec.date_column].desc())
    else:
        order_by.append(table.primary_key.columns.values()[0].asc())

    offset = max(0, (page - 1) * page_size)
    rows_stmt = (
        select(table)
        .where(where)
        .order_by(*order_by)
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(rows_stmt)

    # SQLAlchemy returns rows as RowMapping when iterating with `.mappings()`.
    rows: list[dict[str, Any]] = [dict(row) for row in result.mappings().all()]
    return rows, int(total)


async def get_report_provenance(
    db: AsyncSession,
    *,
    spec: ReportSpec,
    tenant_id: UUID,
) -> dict[str, Any]:
    """Return summary proveniencia for a report (latest ingested row).

    Used by `<DataOriginBadge>` on the detail page. Returns:
        - source_type
        - adapter_version (latest `ingested_by_version`)
        - last_ingested_at
        - trust_level (most common in the dataset; defaults to None)
    """
    table = await _reflect(db, spec.canonical_table)

    tenant_col = table.c.get("tenant_id")
    if tenant_col is None:
        return {"source_type": spec.administradora}

    cols: list[Any] = []
    if "ingested_at" in table.c:
        cols.append(func.max(table.c.ingested_at).label("last_ingested_at"))
    if "ingested_by_version" in table.c:
        cols.append(
            func.max(table.c.ingested_by_version).label("adapter_version")
        )
    if "trust_level" in table.c:
        cols.append(func.max(table.c.trust_level).label("trust_level"))

    if not cols:
        return {"source_type": spec.administradora}

    stmt = select(*cols).where(tenant_col == tenant_id)
    result = await db.execute(stmt)
    row = result.mappings().one_or_none() or {}

    return {
        "source_type": spec.administradora,
        "adapter_version": row.get("adapter_version"),
        "last_ingested_at": _ensure_datetime(row.get("last_ingested_at")),
        "trust_level": row.get("trust_level"),
    }


def _ensure_datetime(value: Any) -> datetime | None:
    """Coerce SQLAlchemy date/datetime result into a datetime, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return None


def resolve_spec_or_404(slug: str) -> ReportSpec:
    """Return spec for a slug or raise ValueError (caller maps to 404)."""
    spec = get_report_spec(slug)
    if spec is None:
        raise ValueError(f"Slug de relatorio desconhecido: {slug!r}")
    return spec
