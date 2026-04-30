"""Metering: append a usage event and decrement the tenant's monthly credits.

Idempotency:
    `request_id` is the LLM provider's request id (UNIQUE in
    `ai_usage_event`). A retry of `record_usage` with the same `request_id`
    is a no-op (returns the existing event row).

Period:
    Credits are accounted per `period_yyyymm = YYYY-MM`. The first usage of
    a tenant in a new month creates the balance row on demand using the
    tenant's `monthly_credit_quota` from `tenant_ai_subscription`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AIProvider, AIUsageStatus, Module
from app.shared.ai.models.credit_balance import AICreditBalance
from app.shared.ai.models.subscription import TenantAISubscription
from app.shared.ai.models.usage_event import AIUsageEvent


@dataclass(slots=True)
class UsageRecord:
    """Input arguments to `record_usage`."""

    request_id: str
    tenant_id: UUID
    user_id: UUID | None
    feature: str
    context_module: Module | None
    provider: AIProvider
    model: str
    prompt_template_version: str | None
    tokens_input: int
    tokens_output: int
    tokens_cached: int
    cost_brl_provider: Decimal
    cost_credits_billed: int
    status: AIUsageStatus
    error_message: str | None = None
    decision_log_id: UUID | None = None


def _period_yyyymm(at: datetime | None = None) -> str:
    at = at or datetime.now(UTC)
    return at.strftime("%Y-%m")


async def record_usage(db: AsyncSession, rec: UsageRecord) -> AIUsageEvent:
    """Append a usage event and decrement credits atomically (caller commits).

    Returns the persisted event. If `rec.request_id` already exists, returns
    the existing row without modifying anything (idempotent retry).
    """
    # Idempotency: if request_id already exists, return existing.
    existing = (
        await db.execute(
            select(AIUsageEvent).where(AIUsageEvent.request_id == rec.request_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    event = AIUsageEvent(
        request_id=rec.request_id,
        tenant_id=rec.tenant_id,
        user_id=rec.user_id,
        feature=rec.feature,
        context_module=rec.context_module,
        provider=rec.provider,
        model=rec.model,
        prompt_template_version=rec.prompt_template_version,
        tokens_input=rec.tokens_input,
        tokens_output=rec.tokens_output,
        tokens_cached=rec.tokens_cached,
        cost_brl_provider=rec.cost_brl_provider,
        cost_credits_billed=rec.cost_credits_billed,
        status=rec.status,
        error_message=rec.error_message,
        decision_log_id=rec.decision_log_id,
    )
    db.add(event)

    # Decrement credits only when call actually happened (OK or successful flag).
    if rec.status == AIUsageStatus.OK and rec.cost_credits_billed > 0:
        await _bump_consumed(db, rec.tenant_id, rec.cost_credits_billed)

    await db.flush()  # populate event.id; caller commits.
    return event


async def _bump_consumed(db: AsyncSession, tenant_id: UUID, delta: int) -> None:
    """Add `delta` to ai_credit_balance.consumed for the current period.

    If no balance row exists for this tenant + period, create one using the
    tenant's monthly_credit_quota.
    """
    period = _period_yyyymm()

    sub = (
        await db.execute(
            select(TenantAISubscription).where(
                TenantAISubscription.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    granted = sub.monthly_credit_quota if sub else 0

    stmt = pg_insert(AICreditBalance).values(
        tenant_id=tenant_id,
        period_yyyymm=period,
        granted=granted,
        consumed=delta,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "period_yyyymm"],
        set_={
            "consumed": AICreditBalance.consumed + delta,
        },
    )
    await db.execute(stmt)


async def get_quota(db: AsyncSession, tenant_id: UUID) -> dict[str, int | bool]:
    """Snapshot of remaining credits for the current period.

    Returns: `{granted, consumed, carryover, topup, remaining, exhausted}`.
    """
    period = _period_yyyymm()
    bal = (
        await db.execute(
            select(AICreditBalance).where(
                AICreditBalance.tenant_id == tenant_id,
                AICreditBalance.period_yyyymm == period,
            )
        )
    ).scalar_one_or_none()

    if bal is None:
        sub = (
            await db.execute(
                select(TenantAISubscription).where(
                    TenantAISubscription.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        granted = sub.monthly_credit_quota if sub else 0
        return {
            "granted": granted,
            "consumed": 0,
            "carryover": 0,
            "topup": 0,
            "remaining": granted,
            "exhausted": granted <= 0,
        }

    return {
        "granted": bal.granted,
        "consumed": bal.consumed,
        "carryover": bal.carryover,
        "topup": bal.topup,
        "remaining": bal.remaining,
        "exhausted": bal.remaining <= 0,
    }
