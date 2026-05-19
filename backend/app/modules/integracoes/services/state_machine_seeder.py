"""State machine seeder — cria rows NOT_STARTED pra dias uteis esperados.

F1.4 do refactor de sync (ver `project_qitech_sync_state_machine` memory).

Job nightly que roda apos consolidacao do calendario (08:00 SP — depois do
watermark_scanner que e 06:00). Pra cada (tenant, source, env, ua, endpoint)
com `enabled=True` (TSEC) E `state_machine_enabled=True` (EndpointSpec),
calcula a janela [today - SEED_RETRO_BD, today + SEED_AHEAD_BD] em dias
uteis e enfileira `INSERT ON CONFLICT DO NOTHING` pra cada dia util da
janela.

Volume estimado:
    - 35 rows/endpoint/dia (30 retro + 5 a frente)
    - REALINVEST com 13 endpoints QiTech enabled = ~455 rows/dia
    - INSERT ON CONFLICT DO NOTHING garante idempotencia — rerun do job
      no mesmo dia nao duplica nem cria load.

Fim de semana / feriado nunca geram row (filtro `eh_dia_util=true` no
calendario). Implica que se a flag `state_machine_enabled` ligar so
no meio do dia, o seed da execucao do dia seguinte ja popula tudo.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.models.endpoint_date_state import EndpointDateState
from app.modules.integracoes.models.tenant_source_endpoint_config import (
    TenantSourceEndpointConfig,
)
from app.modules.integracoes.public import endpoint_catalog
from app.modules.integracoes.services.state_machine import EndpointDateStateValue
from app.shared.endpoint_catalog import EndpointSpec
from app.warehouse.dim_dia_util import DimDiaUtil

logger = logging.getLogger("gr.integracoes.state_machine_seeder")

SEED_RETRO_BD: int = int(os.environ.get("GR_SM_SEED_RETRO_BD", "30"))
SEED_AHEAD_BD: int = int(os.environ.get("GR_SM_SEED_AHEAD_BD", "5"))


# (tenant_id, source_type, ua_id) -> list of (TSEC, EndpointSpec)
_GroupKey = tuple[UUID, SourceType, UUID | None]


def _build_spec_index_by_source() -> dict[SourceType, dict[str, EndpointSpec]]:
    """Lookup global endpoint_name -> EndpointSpec por source. 1x por tick."""
    out: dict[SourceType, dict[str, EndpointSpec]] = {}
    for st in SourceType:
        specs = endpoint_catalog(st)
        if specs:
            out[st] = {s.name: s for s in specs}
    return out


async def _load_business_days(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    start: date,
    end: date,
) -> list[date]:
    """Carrega dias uteis ANBIMA pro range, ordenados asc."""
    stmt = (
        select(DimDiaUtil.data)
        .where(
            DimDiaUtil.tenant_id == tenant_id,
            DimDiaUtil.data.between(start, end),
            DimDiaUtil.eh_dia_util.is_(True),
        )
        .order_by(DimDiaUtil.data.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


def _window_business_dates(
    business_days: list[date],
    *,
    today: date,
    retro_bd: int,
    ahead_bd: int,
) -> list[date]:
    """Janela de N dias uteis retro + M ahead em torno de `today`.

    Inclui `today` se for util. Se today nao for util (final de semana /
    feriado), pega o ultimo util <= today como ancora.

    Defensivo: se business_days nao cobre o range pedido, retorna o que
    tiver (caller responsavel por carregar range amplo o suficiente).
    """
    if not business_days:
        return []
    # Indice do dia util "ancora" — today ou ultimo util antes de today.
    anchor_idx: int = -1
    for i, d in enumerate(business_days):
        if d <= today:
            anchor_idx = i
        else:
            break
    if anchor_idx < 0:
        # Todos os dias uteis sao futuros — nao tem retro pra incluir.
        return business_days[: ahead_bd + 1]
    start_idx = max(0, anchor_idx - retro_bd)
    end_idx = min(len(business_days), anchor_idx + ahead_bd + 1)
    return business_days[start_idx:end_idx]


async def _seed_group(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    ua_id: UUID | None,
    cfgs_with_spec: list[tuple[TenantSourceEndpointConfig, EndpointSpec]],
    today: date,
    now: datetime,
    summary: dict[str, Any],
) -> None:
    """Seeda rows pra todos os endpoints state-machine-enabled de 1 grupo
    (tenant, source, ua).

    Carrega calendario 1x por grupo (todos endpoints compartilham).
    """
    if not cfgs_with_spec:
        return
    # Range em dias corridos amplo o suficiente pra cobrir SEED_RETRO_BD + alguns
    # fins de semana — 2x bd dias corridos com margem cobre folgado.
    cal_start = today - timedelta(days=SEED_RETRO_BD * 2 + 30)
    cal_end = today + timedelta(days=SEED_AHEAD_BD * 2 + 10)
    business_days = await _load_business_days(
        db, tenant_id=tenant_id, start=cal_start, end=cal_end
    )
    target_dates = _window_business_dates(
        business_days,
        today=today,
        retro_bd=SEED_RETRO_BD,
        ahead_bd=SEED_AHEAD_BD,
    )
    if not target_dates:
        logger.warning(
            "state_machine_seeder: sem dias uteis pra tenant=%s — "
            "calendario nao populado pro range?",
            tenant_id,
        )
        return

    # Bulk insert por endpoint enabled (1 statement por endpoint).
    for cfg, _spec in cfgs_with_spec:
        values = [
            {
                "tenant_id": tenant_id,
                "source_type": source_type.value,
                "environment": cfg.environment.name,
                "unidade_administrativa_id": ua_id,
                "endpoint_name": cfg.endpoint_name,
                "data_referencia": d,
                "state": EndpointDateStateValue.NOT_STARTED.value,
                "next_attempt_at": now,
                "attempts_count": 0,
                "created_at": now,
                "updated_at": now,
            }
            for d in target_dates
        ]
        stmt = (
            pg_insert(EndpointDateState)
            .values(values)
            .on_conflict_do_nothing(
                constraint="uq_endpoint_date_state",
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        inserted = result.rowcount or 0
        summary["endpoints_seeded"] += 1
        summary["rows_inserted"] += inserted
        if inserted:
            logger.info(
                "state_machine_seeder: tenant=%s ua=%s endpoint=%s "
                "inserted %d/%d dates (rest pre-existing)",
                tenant_id,
                ua_id,
                cfg.endpoint_name,
                inserted,
                len(target_dates),
            )


async def seed_endpoint_date_states() -> dict[str, Any]:
    """Job principal: varre TSEC enabled cruzando com EndpointSpec state-machine-enabled
    e seeda janela de dias uteis pra cada.

    Returns: summary com counters pra logging.
    """
    summary: dict[str, Any] = {
        "groups_scanned": 0,
        "endpoints_seeded": 0,
        "endpoints_skipped_disabled": 0,
        "rows_inserted": 0,
        "elapsed_seconds": 0.0,
    }
    started_at = datetime.now(UTC)
    today = started_at.date()
    now = started_at

    spec_index_by_source = _build_spec_index_by_source()
    if not spec_index_by_source:
        return summary

    async with AsyncSessionLocal() as db:
        stmt = select(TenantSourceEndpointConfig).where(
            TenantSourceEndpointConfig.enabled.is_(True),
            TenantSourceEndpointConfig.environment == Environment.PRODUCTION,
        )
        configs = list((await db.execute(stmt)).scalars().all())

        # Filtra so endpoints com state_machine_enabled=True no catalogo.
        # Agrupa por (tenant, source, ua) pra carregar calendario 1x por grupo.
        groups: dict[
            _GroupKey, list[tuple[TenantSourceEndpointConfig, EndpointSpec]]
        ] = defaultdict(list)
        for cfg in configs:
            specs = spec_index_by_source.get(cfg.source_type)
            if not specs:
                continue
            spec = specs.get(cfg.endpoint_name)
            if spec is None:
                # Endpoint configurado mas fora do catalogo — TSEC stale.
                continue
            if not spec.state_machine_enabled:
                summary["endpoints_skipped_disabled"] += 1
                continue
            key: _GroupKey = (
                cfg.tenant_id,
                cfg.source_type,
                cfg.unidade_administrativa_id,
            )
            groups[key].append((cfg, spec))

        summary["groups_scanned"] = len(groups)

        for (tenant_id, source_type, ua_id), cfgs_with_spec in groups.items():
            try:
                await _seed_group(
                    db,
                    tenant_id=tenant_id,
                    source_type=source_type,
                    ua_id=ua_id,
                    cfgs_with_spec=cfgs_with_spec,
                    today=today,
                    now=now,
                    summary=summary,
                )
            except Exception as e:
                logger.exception(
                    "state_machine_seeder: grupo (tenant=%s, source=%s, ua=%s) "
                    "falhou: %s",
                    tenant_id,
                    source_type.value,
                    ua_id,
                    e,
                )

    summary["elapsed_seconds"] = round(
        (datetime.now(UTC) - started_at).total_seconds(), 2
    )
    logger.info(
        "state_machine_seeder: groups=%d endpoints_seeded=%d "
        "skipped_disabled=%d rows_inserted=%d elapsed=%.1fs",
        summary["groups_scanned"],
        summary["endpoints_seeded"],
        summary["endpoints_skipped_disabled"],
        summary["rows_inserted"],
        summary["elapsed_seconds"],
    )
    return summary


__all__ = ["SEED_AHEAD_BD", "SEED_RETRO_BD", "seed_endpoint_date_states"]
