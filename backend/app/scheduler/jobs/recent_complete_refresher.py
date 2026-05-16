"""Recent-complete refresher -- re-busca dias 'complete' recentes pra
detectar publicacao parcial-virou-completa que o reconciler nao pega.

Fix B do plano 2026-05-16 (memoria project_qitech_response_semantics).
Sai do mundo "200 = pronto" pro mundo "200 = primeira evidencia, vamos
confirmar". Defesa contra:

- QiTech publica completo as 07:00, sistema pega complete -> fica complete
  pra sempre. Caso feliz, nao muda nada.
- QiTech publica parcial as 07:00, sistema pega partial -> Fix A do
  reconciler ja retenta automaticamente. Nao e o cenario deste job.
- QiTech publica completo as 07:00, sistema pega complete, MAS por algum
  motivo de timing/cache do fornecedor o payload veio sem algum subset
  esperado e o assessor *nao detectou* (perfil ainda nao mapeado pro
  endpoint). Sem refresh, isso fica grudado. Refresh expoe o problema
  porque o upsert seguinte pode trazer mais dados.
- Vendor republica relatorio dias depois com correcao silenciosa
  (acontece com administradora — RF/MEC do 14/05 saiu sem Sub Jr e
  pode ter sido corrigido em 15/05 ou 16/05).

Algoritmo (1x/dia as 18:00 SP — depois do daily_at + adaptive polling +
margem pro vendor consolidar):

    1. Lista (tenant, ua, endpoint) configurados em TSEC.
    2. Pra cada um, identifica datas no lookback (3 uteis atras, excluindo
       D0) onde:
       - existe row em wh_qitech_raw_relatorio
       - http_status = 200 + completeness in ('complete','partial')
       - now() - fetched_at >= MIN_AGE_HOURS (4h por default)
       - count(BackfillJob refresh-attempts ja gravados pra essa data)
         < MAX_REFRESH_ATTEMPTS (3 por default)
    3. Enfileira BackfillJob com created_by='system:refresh_complete'.
       Backfill worker drena na cadencia normal; _sync_endpoint faz
       UPSERT do raw via uq_wh_qitech_raw_relatorio. Mapper recalcula
       completeness; silver e atualizado se mudou.

PARTIAL entrou no candidate set deliberadamente: o Fix A ja cobre PARTIAL
via reconciler, mas o reconciler so olha a janela RECONCILER_LOOKBACK_DAYS
(default 7). PARTIAL com mais de 7 dias util fica fora do reconciler;
este job pega ate D-3 com cap proprio.

Idempotencia: backfill_service ja deduplica datas dentro do job; o cap
de tentativas evita martelar fonte que nao corrige. Skip silencioso quando
ja existe BackfillJob pending/running pra mesma chave (refresher nao
atropela reconciler/manual).
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.coverage import (
    fetch_qitech_coverage,
    qitech_endpoint_supports_coverage,
)
from app.modules.integracoes.models.backfill_job import BackfillJob
from app.modules.integracoes.models.tenant_source_endpoint_config import (
    TenantSourceEndpointConfig,
)
from app.modules.integracoes.services.backfill_service import (
    create_backfill_job,
    list_active_backfill_jobs,
)
from app.warehouse.dim_dia_util import DimDiaUtil

logger = logging.getLogger("gr.scheduler.recent_complete_refresher")

# Cron diario default — 18:00 SP. Apos daily_at dos endpoints (07:00) +
# adaptive polling (Fase 3 quando vier) + margem pro vendor consolidar
# eventuais republicacoes intra-dia.
DAILY_HOUR = 18
DAILY_MINUTE = 0

# Quantos dias uteis atras varremos a cada execucao. D0 nao entra (e
# trabalho do scheduler diario + reconciler regular). 3 uteis cobrem
# tipicamente uma janela onde re-publicacao silenciosa ainda e plausivel.
LOOKBACK_BUSINESS_DAYS: int = int(
    os.environ.get("GR_REFRESH_COMPLETE_LOOKBACK_BUSINESS_DAYS", "3")
)

# Idade minima do fetched_at pra qualificar refresh. Evita gastar chamada
# de API logo apos coleta normal — se acabamos de pegar (1h atras), o
# vendor dificilmente republicou ainda.
MIN_AGE_HOURS: int = int(
    os.environ.get("GR_REFRESH_COMPLETE_MIN_AGE_HOURS", "4")
)

# Cap absoluto de refresh-attempts por (tenant, ua, endpoint, data).
# Apos N refreshes sem mudanca, presume-se que o complete e definitivo —
# para de martelar a fonte. 3 escolhido pra cobrir ate 3 dias do job
# rodando (refresh dia D-1, D-2, D-3, ai para).
MAX_REFRESH_ATTEMPTS: int = int(
    os.environ.get("GR_REFRESH_COMPLETE_MAX_ATTEMPTS", "3")
)

REFRESHER_CREATED_BY = "system:refresh_complete"


async def run() -> dict[str, Any]:
    """Tick diario. Varre TSEC, identifica complete-candidatos, enfileira."""
    summary: dict[str, Any] = {
        "groups_scanned": 0,
        "candidates_found": 0,
        "skipped_active_job": 0,
        "skipped_max_attempts": 0,
        "skipped_too_recent": 0,
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

        groups: dict[
            tuple[UUID, SourceType, UUID | None],
            list[TenantSourceEndpointConfig],
        ] = defaultdict(list)
        for cfg in configs:
            groups[
                (cfg.tenant_id, cfg.source_type, cfg.unidade_administrativa_id)
            ].append(cfg)

        for (tenant_id, source_type, ua_id), cfgs in groups.items():
            if source_type != SourceType.ADMIN_QITECH:
                continue  # Refresher hoje so cobre QiTech
            summary["groups_scanned"] += 1
            try:
                await _scan_group(
                    db,
                    tenant_id=tenant_id,
                    ua_id=ua_id,
                    cfgs=cfgs,
                    summary=summary,
                )
            except Exception as e:
                msg = (
                    f"tenant={tenant_id} ua={ua_id}: "
                    f"{type(e).__name__}: {e}"
                )
                summary["errors"].append(msg)
                logger.exception("refresher: %s", msg)

    logger.info(
        "refresh_complete: groups=%d candidates=%d jobs=%d "
        "skip(active=%d, max_attempts=%d, too_recent=%d) errors=%d",
        summary["groups_scanned"],
        summary["candidates_found"],
        summary["jobs_created"],
        summary["skipped_active_job"],
        summary["skipped_max_attempts"],
        summary["skipped_too_recent"],
        len(summary["errors"]),
    )
    return summary


async def _scan_group(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID | None,
    cfgs: list[TenantSourceEndpointConfig],
    summary: dict[str, Any],
) -> None:
    """Scan de 1 grupo (tenant, ua) — 1 lookup do calendario + 1 query por endpoint."""
    today = datetime.now(UTC).date()
    business_days = await _load_recent_business_days(
        db,
        tenant_id=tenant_id,
        today=today,
        lookback_business_days=LOOKBACK_BUSINESS_DAYS,
    )
    if not business_days:
        return

    range_start = min(business_days)
    range_end = max(business_days)
    now = datetime.now(UTC)
    min_age = timedelta(hours=MIN_AGE_HOURS)

    for cfg in cfgs:
        if not qitech_endpoint_supports_coverage(cfg.endpoint_name):
            continue
        # Reusa o resolver do adapter — ja faz JOIN com completeness e
        # devolve so as colunas que precisamos.
        rows = await fetch_qitech_coverage(
            db,
            endpoint_name=cfg.endpoint_name,
            tenant_id=cfg.tenant_id,
            unidade_administrativa_id=cfg.unidade_administrativa_id,
            start_date=range_start,
            end_date=range_end,
        )

        candidate_dates: list[date] = []
        for r in rows:
            if r.http_status != 200:
                continue
            if r.completeness not in ("complete", "partial"):
                continue
            if r.data_posicao not in business_days:
                continue
            if r.fetched_at is None or (now - r.fetched_at) < min_age:
                summary["skipped_too_recent"] += 1
                continue
            candidate_dates.append(r.data_posicao)

        if not candidate_dates:
            continue

        # Conta refresh-attempts previos via BackfillJob com created_by
        # = REFRESHER_CREATED_BY. Cap evita martelar fonte que nao corrige.
        attempts = await _count_refresh_attempts(
            db,
            tenant_id=cfg.tenant_id,
            unidade_administrativa_id=cfg.unidade_administrativa_id,
            endpoint_name=cfg.endpoint_name,
            dates=candidate_dates,
        )
        eligible_dates = [
            d for d in candidate_dates if attempts.get(d, 0) < MAX_REFRESH_ATTEMPTS
        ]
        skipped = len(candidate_dates) - len(eligible_dates)
        if skipped:
            summary["skipped_max_attempts"] += skipped
        if not eligible_dates:
            continue

        # Dedupe vs backfill ativo da mesma chave — nao atropela reconciler
        # ou backfill manual rodando.
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
            summary["skipped_active_job"] += 1
            continue

        summary["candidates_found"] += len(eligible_dates)
        job = await create_backfill_job(
            db,
            tenant_id=cfg.tenant_id,
            source_type=cfg.source_type,
            environment=cfg.environment,
            unidade_administrativa_id=cfg.unidade_administrativa_id,
            endpoint_name=cfg.endpoint_name,
            dates=eligible_dates,
            created_by=REFRESHER_CREATED_BY,
        )
        summary["jobs_created"] += 1
        logger.info(
            "refresh_complete: enqueued job=%s tenant=%s ua=%s endpoint=%s n_dates=%d",
            job.id,
            cfg.tenant_id,
            cfg.unidade_administrativa_id,
            cfg.endpoint_name,
            len(eligible_dates),
        )


async def _load_recent_business_days(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    today: date,
    lookback_business_days: int,
) -> set[date]:
    """Retorna os N ultimos dias uteis ANBIMA estritamente ANTES de today.

    D0 nao entra — coleta normal cuida dele; refresher e pos-evento.
    Range maximo de busca: lookback_business_days * 2 dias corridos
    (margem pra fim-de-semana + feriado dentro do range).
    """
    if lookback_business_days <= 0:
        return set()
    margin_days = lookback_business_days * 2 + 5
    stmt = (
        select(DimDiaUtil.data)
        .where(
            DimDiaUtil.tenant_id == tenant_id,
            DimDiaUtil.eh_dia_util.is_(True),
            DimDiaUtil.data < today,
            DimDiaUtil.data >= today - timedelta(days=margin_days),
        )
        .order_by(DimDiaUtil.data.desc())
        .limit(lookback_business_days)
    )
    rows = (await db.execute(stmt)).all()
    return {r[0] for r in rows}


async def _count_refresh_attempts(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    endpoint_name: str,
    dates: list[date],
) -> dict[date, int]:
    """Conta BackfillJobs com created_by=REFRESHER_CREATED_BY que tocaram cada data.

    Soma dates_pending + dates_done — failed conta tambem porque consumiu
    chamada API. Range filtra explicitamente pra reduzir scan da tabela.
    """
    if not dates:
        return {}
    stmt = select(
        func.unnest(
            func.array_cat(BackfillJob.dates_pending, BackfillJob.dates_done)
        ).label("d")
    ).where(
        BackfillJob.tenant_id == tenant_id,
        BackfillJob.source_type == SourceType.ADMIN_QITECH.value,
        BackfillJob.endpoint_name == endpoint_name,
        BackfillJob.created_by == REFRESHER_CREATED_BY,
    )
    if unidade_administrativa_id is not None:
        stmt = stmt.where(
            BackfillJob.unidade_administrativa_id == unidade_administrativa_id
        )
    else:
        stmt = stmt.where(BackfillJob.unidade_administrativa_id.is_(None))

    counts: dict[date, int] = dict.fromkeys(dates, 0)
    dates_set = set(dates)
    for row in (await db.execute(stmt)).all():
        d = row[0]
        if d in dates_set:
            counts[d] += 1
    return counts


__all__ = [
    "DAILY_HOUR",
    "DAILY_MINUTE",
    "LOOKBACK_BUSINESS_DAYS",
    "MAX_REFRESH_ATTEMPTS",
    "MIN_AGE_HOURS",
    "REFRESHER_CREATED_BY",
    "run",
]
