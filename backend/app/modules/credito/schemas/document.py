"""Schemas para /credito/dossies/{id}/documents (ciclo do documento)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import DocumentType


class DocumentRead(BaseModel):
    """Visao de um documento do dossie (metadados + extracao)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dossier_id: UUID
    doc_type: DocumentType
    original_filename: str
    mime_type: str | None
    file_size_bytes: int
    extraction_status: str
    ai_extraction: dict | None
    ai_model_used: str | None
    ai_prompt_version: str | None
    extraction_confidence: Decimal | None
    extraction_error: str | None
    uploaded_at: datetime


class ExtractionUpdate(BaseModel):
    """Payload de validacao/edicao dos campos extraidos pelo analista.

    Os `extracted_fields` editados viram a verdade do dossie; o original da
    IA e preservado em `ai_extraction['_ai_original']` (proveniencia §14).
    """

    model_config = ConfigDict(extra="forbid")

    extracted_fields: dict
    confidence: float | None = None
