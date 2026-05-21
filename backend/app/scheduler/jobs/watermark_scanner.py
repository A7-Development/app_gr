"""Watermark scanner -- enfileira backfill_jobs pra gaps recentes (sliding 30d).

Sub-fase 2B do roadmap freshness QiTech (CLAUDE.md memoria
project_qitech_freshness_followups, 2026-05-15). Roda 1x/dia, varre todos
os endpoints configurados em TSEC e detecta gaps nos ultimos 30 dias usando
o coverage service. Pra cada (tenant, source, ua, endpoint) com gaps E sem
backfill ja em andamento, enfileira 1 backfill_job. O backfill_worker
existente drena na cadencia natural (1 data/tick, 5s).

Por que sliding 30d e nao 730d (cobertura completa):
    Watermark resolve cura recente -- publicacao falhou ontem e o dispatcher
    nao saberia retomar sozinho. Cobertura historica (>30d) e o trabalho do
    one-shot scan, rodado manualmente uma vez na ativacao + sob demanda
    quando operador suspeita de furo antigo.

Por que reusar backfill_job e nao iterar dentro do tick:
    Cada sync QiTech leva 500ms-2s. Se 14 endpoints * 5 gaps cada = 70
    chamadas, o tick passaria de 2 minutos -- alem de criar pico de carga.
    Backfill worker drena 1 data/tick (5s), spread suave + UI mostra
    progresso natural via heatmap da aba Cobertura.

Idempotencia: se ja existe backfill pending/running pra mesma chave,
scanner pula -- evita acumular jobs duplicados quando worker esta drenando
mais devagar que o scan diario.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.models.tenant_source_endpoint_config import (
    TenantSourceEndpointConfig,
)
from app.modules.integracoes.services.backfill_service import (
    create_backfill_job,
    list_active_backfill_jobs,
)
from app.modules.integracoes.services.coverage import (
    CoverageStatus,
    get_source_coverage,
)
from app.modules.integracoes.services.endpoint_routing import (
    is_state_machine_enabled,
)

logger = logging.getLogger("gr.scheduler.watermark_scanner")

# Status que voltam ao candidate set a cada tick (2026-05-16):
# GAP (sem row), PARTIAL (200 com subset esperado ausente),
# NOT_PUBLISHED (4xx-as-row). Refletem dias em que o dado ainda
# pode evoluir.
_RETRYABLE_STATUSES = (
    CoverageStatus.GAP,
    CoverageStatus.PARTIAL,
    CoverageStatus.NOT_PUBLISHED,
)

# Sliding window -- quantos dias atras o scanner olha. 30 dias cobre cura
# recente sem se misturar com one-shot scan (cobertura ampla, sob demanda).
LOOKBACK_DAYS = 30

# Cron diario default -- disparado antes do daily_at dos endpoints QiTech
# (tipicamente 07:00 SP). 06:00 SP da margem pro worker drenar gaps de
# ontem antes do operador chegar.
DAILY_HOUR = 6
DAILY_MINUTE = 0


# Tipo do agrupador (tenant, source, ua) -> coverage e por triplete.
_GroupKey = tuple[UUID, SourceType, UUID | None]


async def run() -> dict[str, Any]:
    """Tick diario. Varre TSEC, computa gaps por endpoint, enfileira jobs.

    Agrupa cfgs por (tenant, source, ua) pra chamar `get_source_coverage`
    1x por grupo (devolve todos endpoints daquele source de uma vez) ao
    inves de 1x por endpoint -- evita N+1 redundante na query do coverage.
    """
    summary: dict[str, Any] = {
        "endpoints_scanned": 0,
        "endpoints_with_gaps": 0,
        "endpoints_skipped_active_job": 0,
        "jobs_created": 0,
        "errors": [],
    }

    async with AsyncSessionLocal() as db:
        stmt = select(TenantSourceEndpointConfig).where(
            TenantSourceEndpointConfig.enabled.is_(True),
            TenantSourceEndpointConfig.environment == Environment.PRODUCTION,
            TenantSourceEndpointConfig.schedule_kind != "on_demand",
        )
        configs = list((await db.execute(stmt)).scalars().all())

        groups: dict[_GroupKey, list[TenantSourceEndpointConfig]] = defaultdict(list)
        for cfg in configs:
            key: _GroupKey = (
                cfg.tenant_id,
                cfg.source_type,
                cfg.unidade_administrativa_id,
            )
            groups[key].append(cfg)

        for (tenant_id, source_type, ua_id), cfgs_in_group in groups.items():
            await _scan_group(
                db,
                tenant_id=tenant_id,
                source_type=source_type,
                ua_id=ua_id,
                cfgs=cfgs_in_group,
                summary=summary,
            )

    logger.info(
        "watermark_scanner: scanned=%d with_gaps=%d skipped_active=%d "
        "jobs_created=%d errors=%d",
        summary["endpoints_scanned"],
        summary["endpoints_with_gaps"],
        summary["endpoints_skipped_active_job"],
        summary["jobs_created"],
        len(summary["errors"]),
    )
    return summary


async def _scan_group(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    ua_id: UUID | None,
    cfgs: list[TenantSourceEndpointConfig],
    summary: dict[str, Any],
) -> None:
    """Scan de 1 grupo (tenant, source, ua) -- 1 chamada coverage cobre todos."""
    try:
        coverage = await get_source_coverage(
            db,
            source_type=source_type,
            tenant_id=tenant_id,
            unidade_administrativa_id=ua_id,
            range_days=LOOKBACK_DAYS,
        )
    except Exception as e:
        msg = (
            f"coverage_fetch tenant={tenant_id} source={source_type.value} "
            f"ua={ua_id}: {type(e).__name__}: {e}"
        )
        summary["errors"].append(msg)
        logger.exception("watermark_scanner: %s", msg)
        return

    coverage_by_name = {e.name: e for e in coverage.endpoints}

    for cfg in cfgs:
        # State machine gate (F3, 2026-05-21): endpoints com
        # `state_machine_enabled=True` no catalogo sao processados pelo
        # `state_machine_dispatcher` — watermark_scanner pula pra nao
        # enfileirar backfill_job redundante.
        if is_state_machine_enabled(cfg.source_type, cfg.endpoint_name):
            continue
        summary["endpoints_scanned"] += 1
        try:
            created = await _maybe_enqueue(
                db,
                cfg=cfg,
                endpoint_coverage=coverage_by_name.get(cfg.endpoint_name),
                summary=summary,
            )
            if created:
                summary["jobs_created"] += 1
        except Exception as e:
            msg = (
                f"{cfg.source_type.value}:{cfg.endpoint_name} "
                f"tenant={cfg.tenant_id} ua={cfg.unidade_administrativa_id}: "
                f"{type(e).__name__}: {e}"
            )
            summary["errors"].append(msg)
            logger.exception("watermark_scanner: scan falhou %s", msg)


async def _maybe_enqueue(
    db: AsyncSession,
    *,
    cfg: TenantSourceEndpointConfig,
    endpoint_coverage,
    summary: dict[str, Any],
) -> bool:
    """Decide se enfileira backfill para 1 endpoint. True = enfileirou.

    Skip silencioso quando: endpoint nao suportado, zero datas a curar,
    ou ja existe backfill ativo (pending/running) pra mesma chave.

    Datas retentaveis (2026-05-16): GAP, PARTIAL e NOT_PUBLISHED. GAP
    eh furo total (sem row); PARTIAL eh 200 com subset esperado
    ausente (administradora pode republicar); NOT_PUBLISHED eh 4xx-as-row
    (vendor pode liberar relatorio depois).
    """
    if endpoint_coverage is None or not endpoint_coverage.supported:
        return False
    retryable_total = (
        endpoint_coverage.count_gap
        + endpoint_coverage.count_partial
        + endpoint_coverage.count_not_published
    )
    if retryable_total <= 0:
        return False

    gap_dates = [
        d.data
        for d in endpoint_coverage.days
        if d.status in _RETRYABLE_STATUSES
    ]
    if not gap_dates:
        return False

    summary["endpoints_with_gaps"] += 1

    # Dedupe vs backfill ativo da mesma chave. list_active_backfill_jobs
    # nao filtra por UA hoje -- filtramos aqui.
    active = await list_active_backfill_jobs(
        db,
        tenant_id=cfg.tenant_id,
        source_type=cfg.source_type,
        endpoint_name=cfg.endpoint_name,
    )
    active_same_ua = [
        j for j in active
        if j.unidade_administrativa_id == cfg.unidade_administrativa_id
    ]
    if active_same_ua:
        summary["endpoints_skipped_active_job"] += 1
        return False

    job = await create_backfill_job(
        db,
        tenant_id=cfg.tenant_id,
        source_type=cfg.source_type,
        environment=cfg.environment,
        unidade_administrativa_id=cfg.unidade_administrativa_id,
        endpoint_name=cfg.endpoint_name,
        dates=gap_dates,
        created_by="system:watermark_scanner",
    )
    logger.info(
        "watermark_scanner: enfileirou job=%s tenant=%s source=%s ua=%s "
        "endpoint=%s n_gaps=%d",
        job.id,
        cfg.tenant_id,
        cfg.source_type.value,
        cfg.unidade_administrativa_id,
        cfg.endpoint_name,
        len(gap_dates),
    )
    return True
