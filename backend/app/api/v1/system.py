"""System-level endpoints (cross-cutting, non-module).

Exposes pipeline health so the frontend can surface "when did data last
arrive" independently of any dashboard filter.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.audit_log.sync_health import last_sync_at

router = APIRouter(prefix="/system", tags=["system"])


class SyncHealthEntry(BaseModel):
    """Health snapshot of a single ingestion pipeline."""

    last_sync_at: datetime | None = Field(
        default=None,
        description="Timestamp of the most recent SUCCESSFUL sync (decision_log).",
    )
    adapter_version: str | None = Field(
        default=None, description="Adapter version that produced the last sync."
    )


# Mapping `source_type (public key) -> rule_or_model (decision_log)`.
# Extended when new adapters start logging SYNC entries.
_ADAPTER_BY_SOURCE: dict[str, str] = {
    "erp:bitfin": "bitfin_adapter",
}


@router.get("/sync-health", response_model=dict[str, SyncHealthEntry])
async def sync_health(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, SyncHealthEntry]:
    """Return the last successful sync per known adapter for the current tenant.

    Public-fonte-FDW sources (CVM, Bacen) are not listed here — their
    ingestion lives in separate repos and doesn't write to decision_log.
    """
    out: dict[str, SyncHealthEntry] = {}
    for source_type, rule in _ADAPTER_BY_SOURCE.items():
        ts = await last_sync_at(db, principal.tenant_id, rule_or_model=rule)
        out[source_type] = SyncHealthEntry(last_sync_at=ts)
    return out
