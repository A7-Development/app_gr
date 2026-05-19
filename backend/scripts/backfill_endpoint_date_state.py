"""Backfill da tabela endpoint_date_state a partir do raw layer.

F2 do refactor de sync (ver `project_qitech_sync_state_machine` memory).

Roda **uma vez por ambiente** antes de ligar `state_machine_enabled=True`
no piloto. Sem este script, o nightly seeder vai criar 36 rows NOT_STARTED
e o dispatcher vai chamar QiTech 36 vezes pra redescobrir o que ja temos
em wh_qitech_raw_relatorio.

Algoritmo:
1. Lista (tenant, source, env, ua, endpoint) com state_machine_enabled=True
   no catalogo E enabled=true em TSEC.
2. Pra cada combinacao: chama `fetch_qitech_coverage(range)` que ja sabe
   mapear endpoint_name -> tabela raw correta.
3. Pra cada CoverageRow: `derive_state_from_result(http_status, completeness)`
   produz estado canonico. `compute_next_attempt` calcula next_attempt_at
   (TTL pra COMPLETE, backoff pra retentaveis, NULL pra ABANDONED).
4. INSERT ON CONFLICT DO NOTHING — re-rodar e idempotente.

Uso:
    python -m scripts.backfill_endpoint_date_state --tenant <slug-ou-uuid>
    python -m scripts.backfill_endpoint_date_state --tenant realinvest --range-days 60 --dry-run
    python -m scripts.backfill_endpoint_date_state --all-tenants

`--all-tenants` itera por todos os tenants — usar quando state_machine
for ativada em multi-tenant. Default e um por chamada.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.coverage import (
    fetch_qitech_coverage,
)
from app.modules.integracoes.models.endpoint_date_state import EndpointDateState
from app.modules.integracoes.models.tenant_source_endpoint_config import (
    TenantSourceEndpointConfig,
)
from app.modules.integracoes.public import endpoint_catalog
from app.modules.integracoes.services.state_machine import (
    compute_next_attempt,
    derive_state_from_result,
)
from app.modules.integracoes.services.tolerance import (
    ToleranceWindow,
    resolve_tolerance_window,
)
from app.shared.endpoint_catalog import EndpointSpec
from app.shared.identity.tenant import Tenant
from app.warehouse.dim_dia_util import DimDiaUtil

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("backfill_endpoint_date_state")


async def _resolve_tenant(db: AsyncSession, tenant_arg: str) -> Tenant:
    """Aceita UUID ou slug. Levanta se nao achar."""
    try:
        tid = UUID(tenant_arg)
        t = await db.get(Tenant, tid)
    except ValueError:
        stmt = select(Tenant).where(Tenant.slug == tenant_arg)
        t = (await db.execute(stmt)).scalar_one_or_none()
    if t is None:
        raise SystemExit(f"Tenant nao encontrado: {tenant_arg!r}")
    return t


async def _list_tenants(db: AsyncSession) -> list[Tenant]:
    stmt = select(Tenant)
    return list((await db.execute(stmt)).scalars().all())


async def _list_business_days(
    db: AsyncSession, *, tenant_id: UUID, start: date, end: date
) -> frozenset[date]:
    stmt = select(DimDiaUtil.data).where(
        DimDiaUtil.tenant_id == tenant_id,
        DimDiaUtil.data.between(start, end),
        DimDiaUtil.eh_dia_util.is_(True),
    )
    return frozenset((await db.execute(stmt)).scalars().all())


async def _resolve_tolerance(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment,
    unidade_administrativa_id: UUID | None,
    endpoint_name: str,
    spec: EndpointSpec,
) -> ToleranceWindow | None:
    stmt = select(
        TenantSourceEndpointConfig.expected_lag_business_days_override,
        TenantSourceEndpointConfig.tolerance_business_days_override,
        TenantSourceEndpointConfig.give_up_business_days_override,
    ).where(
        TenantSourceEndpointConfig.tenant_id == tenant_id,
        TenantSourceEndpointConfig.source_type == source_type,
        TenantSourceEndpointConfig.environment == environment,
        TenantSourceEndpointConfig.endpoint_name == endpoint_name,
    )
    if unidade_administrativa_id is None:
        stmt = stmt.where(
            TenantSourceEndpointConfig.unidade_administrativa_id.is_(None)
        )
    else:
        stmt = stmt.where(
            TenantSourceEndpointConfig.unidade_administrativa_id
            == unidade_administrativa_id
        )
    row = (await db.execute(stmt)).first()
    ov = row if row is not None else (None, None, None)
    try:
        return resolve_tolerance_window(
            expected_lag_override=ov[0],
            tolerance_override=ov[1],
            give_up_override=ov[2],
            default_expected_lag=spec.default_expected_lag_business_days,
            default_tolerance=spec.default_tolerance_business_days,
            default_give_up=spec.default_give_up_business_days,
        )
    except ValueError:
        return None


async def _backfill_endpoint(
    db: AsyncSession,
    *,
    tenant: Tenant,
    source_type: SourceType,
    environment: Environment,
    ua_id: UUID | None,
    endpoint_name: str,
    spec: EndpointSpec,
    range_days: int,
    dry_run: bool,
    summary: dict[str, Any],
) -> None:
    """Backfill 1 endpoint pra 1 (tenant, ua) — varre coverage + insert."""
    today = datetime.now(UTC).date()
    now = datetime.now(UTC)
    start = today - timedelta(days=range_days)

    # Carrega calendario amplo (range + buffer pra calculo de TTL/backoff).
    cal_start = start - timedelta(days=30)
    cal_end = today + timedelta(days=15)
    business_days_set = await _list_business_days(
        db, tenant_id=tenant.id, start=cal_start, end=cal_end
    )

    window = await _resolve_tolerance(
        db,
        tenant_id=tenant.id,
        source_type=source_type,
        environment=environment,
        unidade_administrativa_id=ua_id,
        endpoint_name=endpoint_name,
        spec=spec,
    )
    if window is None:
        logger.warning(
            "tenant=%s endpoint=%s: combinacao override+default viola "
            "monotonicidade — pulando",
            tenant.slug,
            endpoint_name,
        )
        return

    coverage_rows = await fetch_qitech_coverage(
        db,
        endpoint_name=endpoint_name,
        tenant_id=tenant.id,
        unidade_administrativa_id=ua_id,
        start_date=start,
        end_date=today,
    )
    if not coverage_rows:
        summary["endpoints_no_history"] += 1
        return

    # Dedupe — caller pode receber > 1 row pra (endpoint, data) em endpoints
    # range-based. Manter a mais recente por fetched_at.
    by_date: dict[date, Any] = {}
    for r in coverage_rows:
        existing = by_date.get(r.data_posicao)
        if existing is None or (
            r.fetched_at and existing.fetched_at
            and r.fetched_at > existing.fetched_at
        ):
            by_date[r.data_posicao] = r

    values: list[dict[str, Any]] = []
    for d, r in by_date.items():
        state = derive_state_from_result(
            http_status=r.http_status, completeness=r.completeness
        )
        next_attempt_at, backoff_seconds, final_state = compute_next_attempt(
            new_state=state,
            data_referencia=d,
            today=today,
            now=now,
            business_days_set=business_days_set,
            window=window,
            refresh_complete_window_business_days=(
                spec.refresh_complete_window_business_days
            ),
        )
        values.append(
            {
                "tenant_id": tenant.id,
                "source_type": source_type.value,
                "environment": environment.name,
                "unidade_administrativa_id": ua_id,
                "endpoint_name": endpoint_name,
                "data_referencia": d,
                "state": final_state.value,
                "next_attempt_at": next_attempt_at,
                "attempts_count": 1,  # ja teve 1 fetch (o que populou raw)
                "last_attempt_at": r.fetched_at,
                "last_http_status": r.http_status,
                "last_completeness": r.completeness,
                "backoff_seconds": backoff_seconds,
                "created_at": now,
                "updated_at": now,
            }
        )

    if dry_run:
        sample = values[0] if values else {}
        logger.info(
            "[DRY] tenant=%s endpoint=%s: %d rows seriam inseridas. "
            "Sample: state=%s next=%s",
            tenant.slug,
            endpoint_name,
            len(values),
            sample.get("state"),
            sample.get("next_attempt_at"),
        )
        summary["endpoints_processed"] += 1
        summary["rows_would_insert"] += len(values)
        return

    stmt = (
        pg_insert(EndpointDateState)
        .values(values)
        .on_conflict_do_nothing(constraint="uq_endpoint_date_state")
    )
    result = await db.execute(stmt)
    await db.commit()
    inserted = result.rowcount or 0
    by_state: dict[str, int] = {}
    for v in values:
        by_state[v["state"]] = by_state.get(v["state"], 0) + 1
    logger.info(
        "tenant=%s endpoint=%s: inserted=%d/%d (rest pre-existing). "
        "by_state=%s",
        tenant.slug,
        endpoint_name,
        inserted,
        len(values),
        by_state,
    )
    summary["endpoints_processed"] += 1
    summary["rows_inserted"] += inserted


async def _backfill_tenant(
    db: AsyncSession,
    *,
    tenant: Tenant,
    source_type: SourceType,
    range_days: int,
    only: str | None,
    dry_run: bool,
    summary: dict[str, Any],
) -> None:
    """Backfill todos os endpoints state-machine-enabled de 1 tenant."""
    specs = endpoint_catalog(source_type)
    enabled_specs = {
        s.name: s for s in specs if s.state_machine_enabled
    }
    if not enabled_specs:
        logger.info("Nenhum endpoint state-machine-enabled em %s", source_type.value)
        return

    stmt = select(TenantSourceEndpointConfig).where(
        TenantSourceEndpointConfig.tenant_id == tenant.id,
        TenantSourceEndpointConfig.source_type == source_type,
        TenantSourceEndpointConfig.environment == Environment.PRODUCTION,
        TenantSourceEndpointConfig.enabled.is_(True),
    )
    cfgs = list((await db.execute(stmt)).scalars().all())
    if not cfgs:
        logger.info(
            "tenant=%s: sem TSEC enabled pra %s",
            tenant.slug,
            source_type.value,
        )
        return

    for cfg in cfgs:
        spec = enabled_specs.get(cfg.endpoint_name)
        if spec is None:
            summary["endpoints_skipped_not_enabled"] += 1
            continue
        if only and cfg.endpoint_name != only:
            continue
        await _backfill_endpoint(
            db,
            tenant=tenant,
            source_type=source_type,
            environment=Environment.PRODUCTION,
            ua_id=cfg.unidade_administrativa_id,
            endpoint_name=cfg.endpoint_name,
            spec=spec,
            range_days=range_days,
            dry_run=dry_run,
            summary=summary,
        )


async def _main(args: argparse.Namespace) -> None:
    source_type = SourceType(args.source_type)
    summary: dict[str, Any] = {
        "tenants_processed": 0,
        "endpoints_processed": 0,
        "endpoints_skipped_not_enabled": 0,
        "endpoints_no_history": 0,
        "rows_inserted": 0,
        "rows_would_insert": 0,
    }

    async with AsyncSessionLocal() as db:
        if args.all_tenants:
            tenants = await _list_tenants(db)
        else:
            tenants = [await _resolve_tenant(db, args.tenant)]
        for tenant in tenants:
            logger.info("=== tenant=%s (%s) ===", tenant.slug, tenant.id)
            await _backfill_tenant(
                db,
                tenant=tenant,
                source_type=source_type,
                range_days=args.range_days,
                only=args.only,
                dry_run=args.dry_run,
                summary=summary,
            )
            summary["tenants_processed"] += 1

    logger.info("=== SUMMARY ===")
    for k, v in summary.items():
        logger.info("  %s = %s", k, v)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill endpoint_date_state a partir do raw layer (F2)"
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--tenant",
        help="UUID ou slug do tenant. Use --all-tenants pra todos.",
    )
    g.add_argument(
        "--all-tenants", action="store_true", help="Roda pra todos os tenants."
    )
    p.add_argument(
        "--source-type",
        default="admin:qitech",
        help="SourceType (default admin:qitech).",
    )
    p.add_argument(
        "--range-days",
        type=int,
        default=60,
        help=(
            "Dias corridos de retroatividade. Default 60 — cobre folgado a "
            "janela de 30 dias uteis do seeder + buffer."
        ),
    )
    p.add_argument(
        "--only",
        help="Limita a 1 endpoint (ex.: market.conta_corrente).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Nao insere — so loga o que seria inserido.",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(_main(args))
