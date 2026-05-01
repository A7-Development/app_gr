"""Pydantic schemas for /credito/templates endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import DocumentType


class DocumentTemplateUpsert(BaseModel):
    """Input to create/update a document extraction template."""

    model_config = ConfigDict(extra="forbid")

    doc_type: DocumentType
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    fields_schema: dict[str, Any] = Field(default_factory=dict)
    instructions: str | None = None
    active: bool = True


class DocumentTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID | None
    doc_type: DocumentType
    name: str
    description: str | None
    fields_schema: dict[str, Any]
    instructions: str | None
    active: bool
    created_at: datetime
    updated_at: datetime
