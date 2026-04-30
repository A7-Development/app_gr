"""Rate limit + cost cap (in-memory MVP, Redis-backed in Phase 2).

Three independent dimensions per tenant:
    - RPM (requests per minute) — token bucket of fixed size.
    - TPM (tokens per minute, output) — token bucket scaled by tokens consumed.
    - BRL/day — cumulative cost cap, refreshed at UTC midnight.

The MVP uses a process-local dict; this is fine for single-worker dev. For
multi-worker prod, Phase 2 swaps the backend to Redis (same interface).

Hard caps come from `tenant_ai_subscription.hard_cap_brl`. Soft caps (alerts
at 50/75/90%) live in the metering job, not here.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID


@dataclass(slots=True)
class _Bucket:
    """One token-bucket cell."""

    capacity: int
    tokens: float
    last_refill: datetime


@dataclass(slots=True)
class _DayCost:
    """Cumulative BRL cost in a UTC day."""

    day: date
    total: Decimal = Decimal("0")


@dataclass(slots=True)
class _TenantState:
    rpm: _Bucket | None = None
    tpm: _Bucket | None = None
    cost: _DayCost = field(
        default_factory=lambda: _DayCost(day=datetime.now(UTC).date())
    )


class RateLimitError(Exception):
    """Raised when a tenant exceeds RPM, TPM, or BRL/day."""

    def __init__(self, dimension: str, message: str) -> None:
        super().__init__(message)
        self.dimension = dimension


# Conservative MVP defaults. Per-plan overrides come from tenant_ai_subscription.
_DEFAULT_RPM = 30
_DEFAULT_TPM = 60_000

_state: dict[UUID, _TenantState] = {}
_lock = asyncio.Lock()


def _refill(bucket: _Bucket, capacity: int, refill_per_min: int) -> None:
    now = datetime.now(UTC)
    elapsed = (now - bucket.last_refill).total_seconds()
    bucket.tokens = min(capacity, bucket.tokens + (elapsed / 60.0) * refill_per_min)
    bucket.last_refill = now


async def check_rpm(tenant_id: UUID, *, capacity: int = _DEFAULT_RPM) -> None:
    """Reserve 1 RPM token for `tenant_id`. Raises RateLimitError on empty."""
    async with _lock:
        st = _state.setdefault(tenant_id, _TenantState())
        if st.rpm is None:
            st.rpm = _Bucket(
                capacity=capacity, tokens=float(capacity), last_refill=datetime.now(UTC)
            )
        _refill(st.rpm, capacity, capacity)
        if st.rpm.tokens < 1:
            raise RateLimitError(
                "rpm",
                f"Limite de requests por minuto atingido ({capacity}). Aguarde alguns segundos.",
            )
        st.rpm.tokens -= 1


async def reserve_tpm(
    tenant_id: UUID, *, predicted_tokens: int, capacity: int = _DEFAULT_TPM
) -> None:
    """Try to consume `predicted_tokens` from the TPM bucket. Raises on overflow.

    `predicted_tokens` should be a generous upper bound (e.g. max_tokens + 500).
    Actual usage is reconciled in metering after the call.
    """
    async with _lock:
        st = _state.setdefault(tenant_id, _TenantState())
        if st.tpm is None:
            st.tpm = _Bucket(
                capacity=capacity, tokens=float(capacity), last_refill=datetime.now(UTC)
            )
        _refill(st.tpm, capacity, capacity)
        if st.tpm.tokens < predicted_tokens:
            raise RateLimitError(
                "tpm",
                f"Limite de tokens por minuto atingido (~{capacity}). Aguarde 30-60s.",
            )
        st.tpm.tokens -= predicted_tokens


async def check_daily_cost_cap(
    tenant_id: UUID, *, hard_cap_brl: Decimal | None
) -> None:
    """Refuse the call if the tenant already hit its daily BRL cap."""
    if hard_cap_brl is None:
        return
    async with _lock:
        st = _state.setdefault(tenant_id, _TenantState())
        today = datetime.now(UTC).date()
        if st.cost.day != today:
            st.cost = _DayCost(day=today)
        if st.cost.total >= hard_cap_brl:
            raise RateLimitError(
                "brl_day",
                f"Limite diario de R$ {hard_cap_brl} atingido. Tente novamente amanha.",
            )


async def record_cost(tenant_id: UUID, *, cost_brl: Decimal) -> None:
    """Increment the day's cumulative cost (called after a successful call)."""
    async with _lock:
        st = _state.setdefault(tenant_id, _TenantState())
        today = datetime.now(UTC).date()
        if st.cost.day != today:
            st.cost = _DayCost(day=today)
        st.cost.total += cost_brl


async def reset() -> None:
    """Test-only: wipe all state. Useful between tests."""
    async with _lock:
        _state.clear()


async def snapshot(tenant_id: UUID) -> dict:
    """Diagnostic snapshot of one tenant's buckets (admin telemetry)."""
    async with _lock:
        st = _state.get(tenant_id)
        if st is None:
            return {"rpm": None, "tpm": None, "cost_today": "0", "day": str(datetime.now(UTC).date())}
        return {
            "rpm": None if st.rpm is None else round(st.rpm.tokens, 1),
            "tpm": None if st.tpm is None else round(st.tpm.tokens, 1),
            "cost_today": str(st.cost.total),
            "day": str(st.cost.day),
        }


# Soft remaining-window helper used by the chat orchestrator to refuse calls
# when the BRL/day cap is exhausted before issuing the call (cheaper than 429
# after-the-fact, as the call already happened upstream).
async def add_soft_predicted_cost(
    tenant_id: UUID, *, predicted_brl: Decimal, hard_cap_brl: Decimal | None
) -> None:
    """Like record_cost but BEFORE the call, used as a guardrail. Caller must
    call `record_cost` again with the *actual* delta after the call to keep
    the running total accurate.

    For MVP we treat the predicted cost as an over-reservation: if it would
    cross the cap, refuse. After the actual call, the metering layer reconciles.
    """
    if hard_cap_brl is None:
        return
    async with _lock:
        st = _state.setdefault(tenant_id, _TenantState())
        today = datetime.now(UTC).date()
        if st.cost.day != today:
            st.cost = _DayCost(day=today)
        if st.cost.total + predicted_brl > hard_cap_brl:
            raise RateLimitError(
                "brl_day",
                f"Esta chamada ultrapassaria o limite diario de R$ {hard_cap_brl}.",
            )


def time_until_midnight_utc() -> timedelta:
    """Helper for retry-after headers when BRL/day exhausted."""
    now = datetime.now(UTC)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return tomorrow - now
