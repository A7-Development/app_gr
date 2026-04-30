"""GET /api/v1/ai/insights — auto 3 bullets for a page."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_guard import require_ai
from app.core.database import get_db
from app.core.enums import AICapability
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.ai.schemas import InsightItem, InsightsResponse
from app.shared.ai.services.insight_generator import generate_insights

router = APIRouter(prefix="/insights")


# In-process cache: (tenant_id, page, period, filters_hash) -> (expires_at, payload)
_CACHE_TTL = timedelta(minutes=10)
_cache: dict[tuple, tuple[datetime, dict]] = {}


def _cache_key(
    tenant_id: str, page: str, period: str | None, filters: str | None
) -> tuple:
    h = hashlib.sha256((filters or "").encode("utf-8")).hexdigest()[:16]
    return (tenant_id, page, period or "", h)


@router.get("", response_model=InsightsResponse)
async def get_insights(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_ai(AICapability.READ))],
    page: Annotated[str, Query(min_length=1)],
    period: Annotated[str | None, Query()] = None,
    filters: Annotated[str | None, Query()] = None,
    kpis_block: Annotated[str | None, Query(max_length=8000)] = None,
) -> InsightsResponse:
    """Return 3 short bullets for the given page context.

    Server-side cache by (tenant, page, period, filters) for 10 minutes to
    contain cost. Pass `kpis_block` (text) with the page's current KPIs;
    without it the call is a no-op (returns empty list).
    """
    key = _cache_key(str(principal.tenant_id), page, period, filters)
    now = datetime.now(UTC)
    cached = _cache.get(key)
    if cached and cached[0] > now:
        data = cached[1]
    elif not kpis_block:
        # No data to feed the LLM, no point burning credits.
        data = {"insights": [], "generated_at": now.isoformat()}
    else:
        data = await generate_insights(
            db=db,
            principal=principal,
            page=page,
            period=period,
            kpis_block=kpis_block,
        )
        _cache[key] = (now + _CACHE_TTL, data)

    return InsightsResponse(
        insights=[InsightItem(**i) for i in data.get("insights", [])],
        generated_at=datetime.fromisoformat(data["generated_at"]),
    )
