"""Health of ingestion pipelines (decision_log as source of truth).

Exposes `last_sync_at()`: the timestamp of the most recent successful SYNC
entry in `decision_log` for a given adapter. Global per tenant — independent
of any dashboard filter — so the frontend can distinguish "pipeline is alive"
from "filtered data is recent".

Used by:
- BI services to enrich `Provenance.last_sync_at`
- Cross-cutting endpoint `/system/sync-health` for module-wide status widgets
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.audit_log.decision_log import DecisionLog, DecisionType


async def last_sync_at(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    rule_or_model: str,
    endpoint_name: str | None = None,
) -> datetime | None:
    """Return the `occurred_at` of the most recent successful SYNC for this adapter.

    A sync is considered successful when `explanation == 'OK'` (convention from
    `bitfin.etl.sync_all`). Failed or partial syncs are ignored — the caller
    wants to know "when did fresh data last arrive", not "when did we last try".

    `endpoint_name`:
        - `None` (default): sem filtro — comportamento legado (entry pode ter
          endpoint_name preenchido ou nao).
        - String: filtra por endpoint especifico, util quando o caller quer
          "ultima sync OK do endpoint X" (ex.: TSEC.last_sync_at na UI).

    Returns None when no successful sync exists yet for this tenant/adapter.
    """
    stmt = (
        select(func.max(DecisionLog.occurred_at))
        .where(
            DecisionLog.tenant_id == tenant_id,
            DecisionLog.decision_type == DecisionType.SYNC,
            DecisionLog.rule_or_model == rule_or_model,
            DecisionLog.explanation == "OK",
        )
    )
    if endpoint_name is not None:
        stmt = stmt.where(DecisionLog.endpoint_name == endpoint_name)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def last_data_update_at(
    db: AsyncSession,
    tenant_id: UUID,
    model: Any,
) -> datetime | None:
    """Return `MAX(ingested_at)` for a silver table — when did fresh data
    actually land in this tenant's slice of `<model>`.

    Use this (not `last_sync_at`) when the UI question is "how stale is the
    data the user is looking at right now". Survives partial sync failures:
    if 9 of 10 sub-tasks succeeded and one failed, `ingested_at` on the rows
    that DID update is fresh — `last_sync_at` would still report the previous
    fully-OK run.

    `model` must have a `tenant_id` column and inherit `Auditable`
    (so `ingested_at` exists).
    """
    stmt = select(func.max(model.ingested_at)).where(model.tenant_id == tenant_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def last_sync_attempt_at(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    rule_or_model: str,
    endpoint_name: str | None = None,
) -> datetime | None:
    """Return `occurred_at` of the most recent SYNC attempt — success OR failure.

    Used by the scheduler dispatcher to enforce backoff between attempts. If
    a sync is failing, we still want to wait `sync_frequency_minutes` between
    retries instead of hammering the upstream every tick.

    `endpoint_name`:
        - `None` (default): comportamento legado — pega ultima tentativa do
          adapter inteiro. Usado pelo dispatcher modo legado.
        - String: filtra por endpoint. Usado pelo dispatcher modo novo +
          backoff por endpoint.

    Differs from `last_sync_at` (which filters `explanation='OK'`) — for UI
    "last fresh data" use that; for "when did we last hit the API" use this.
    """
    stmt = select(func.max(DecisionLog.occurred_at)).where(
        DecisionLog.tenant_id == tenant_id,
        DecisionLog.decision_type == DecisionType.SYNC,
        DecisionLog.rule_or_model == rule_or_model,
    )
    if endpoint_name is not None:
        stmt = stmt.where(DecisionLog.endpoint_name == endpoint_name)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
