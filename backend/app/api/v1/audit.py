"""Audit endpoints — template demonstrating the provenance pattern.

Every analytical endpoint (BI, reconciliacao, etc) should follow `/audit/ping`
as the canonical shape: return data + proveniencia metadata.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.schemas import AuditPingResponse
from app.core.tenant_middleware import RequestPrincipal, get_current_principal

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/ping", response_model=AuditPingResponse)
async def audit_ping(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
) -> AuditPingResponse:
    """Template endpoint: returns a fictitious value with full provenance metadata.

    Used in Sprint 1 to validate the pattern end-to-end. Replaced by real BI
    endpoints in Sprint 4 that follow this same shape.
    """
    return AuditPingResponse(
        value=42.0,
        label="Audit ping",
        source_type="derived",
        source_id=f"audit-ping-{principal.tenant_id}",
        ingested_at=datetime.now(UTC),
        source_updated_at=None,
        trust_level="high",
        ingested_by_version="audit_ping_v0.1.0",
    )
