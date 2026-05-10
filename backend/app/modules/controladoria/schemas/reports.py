"""Controladoria · Relatorios — Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import Permission, SourceType
from app.modules.integracoes.report_catalog import (
    ReportCategory,
    ReportRefreshKind,
)


class ReportCardResponse(BaseModel):
    """Compact view of a report — used by `<RelatorioCard>` in the catalog page."""

    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str
    description: str
    category: ReportCategory
    administradora: SourceType
    endpoint_name: str
    canonical_table: str
    refresh_kind: ReportRefreshKind
    has_date_filter: bool
    has_fund_filter: bool
    default_permission: Permission


class CatalogResponse(BaseModel):
    """Full catalog response — list of cards, plus metadata for the page."""

    reports: list[ReportCardResponse]
    total: int


class ProvenanceMetadata(BaseModel):
    """Per-response provenance summary (CLAUDE.md §14.5).

    Surfaced in `<DataOriginBadge>` at the top of detail pages.
    """

    source_type: SourceType
    adapter_version: str | None = None
    last_ingested_at: datetime | None = None
    trust_level: str | None = None


class RowsResponse(BaseModel):
    """Generic rows response for `GET /relatorios/<slug>`.

    Columns vary per slug; frontend has TS-types in `frontend/src/lib/reports/<slug>.ts`
    that interpret each row.
    """

    rows: list[dict[str, Any]] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    provenance: ProvenanceMetadata
