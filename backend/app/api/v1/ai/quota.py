"""GET /api/v1/ai/quota — current monthly credit balance for the tenant."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_guard import require_ai
from app.core.database import get_db
from app.core.enums import AICapability
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.ai.schemas import QuotaResponse
from app.shared.ai.services.metering import get_quota

router = APIRouter()


@router.get("/quota", response_model=QuotaResponse)
async def get_ai_quota(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_ai(AICapability.READ))],
) -> QuotaResponse:
    """Snapshot of remaining credits + period."""
    snap = await get_quota(db, principal.tenant_id)
    return QuotaResponse(
        granted=int(snap["granted"]),
        consumed=int(snap["consumed"]),
        carryover=int(snap["carryover"]),
        topup=int(snap["topup"]),
        remaining=int(snap["remaining"]),
        exhausted=bool(snap["exhausted"]),
        period_yyyymm=datetime.now(UTC).strftime("%Y-%m"),
    )
