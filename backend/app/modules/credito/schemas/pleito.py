"""Pydantic schemas for the pleito (credit request) flow."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PleitoUpsert(BaseModel):
    """Input to create/update the structured pleito."""

    model_config = ConfigDict(extra="forbid")

    produto: str | None = Field(None, max_length=64)
    volume_brl: Decimal | None = None
    taxa: str | None = Field(None, max_length=128)
    prazo: str | None = Field(None, max_length=128)
    contexto: str | None = None
    urgencia: str | None = Field(None, pattern="^(alta|media|baixa)$")
    source_text: str | None = None
    extracted_by_ai: bool = False


class PleitoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dossier_id: UUID
    produto: str | None
    volume_brl: Decimal | None
    taxa: str | None
    prazo: str | None
    contexto: str | None
    urgencia: str | None
    source_text: str | None
    extracted_by_ai: bool
    created_at: datetime
    updated_at: datetime


class PleitoExtractRequest(BaseModel):
    """Input to extract structured pleito fields from informal text."""

    model_config = ConfigDict(extra="forbid")

    informal_text: str = Field(..., min_length=10)
