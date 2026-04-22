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
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.audit_log.decision_log import DecisionLog, DecisionType


async def last_sync_at(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    rule_or_model: str,
) -> datetime | None:
    """Return the `occurred_at` of the most recent successful SYNC for this adapter.

    A sync is considered successful when `explanation == 'OK'` (convention from
    `bitfin.etl.sync_all`). Failed or partial syncs are ignored — the caller
    wants to know "when did fresh data last arrive", not "when did we last try".

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
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
