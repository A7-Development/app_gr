"""Pydantic schemas for /credito/checklist endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import CheckSeverity


class ChecklistItemUpsert(BaseModel):
    """Input to create/update a checklist item."""

    model_config = ConfigDict(extra="forbid")

    section: str = Field(..., min_length=1, max_length=64)
    code: str = Field(..., min_length=1, max_length=32)
    description: str = Field(..., min_length=1)
    guidance: str | None = None
    severity: CheckSeverity = CheckSeverity.IMPORTANT
    auto_evaluable: bool = True
    order_index: int = 0
    active: bool = True


class ChecklistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID | None
    section: str
    code: str
    description: str
    guidance: str | None
    severity: CheckSeverity
    auto_evaluable: bool
    order_index: int
    active: bool
    created_at: datetime
