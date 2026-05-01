"""Pydantic schemas for Specialist Agents' structured outputs.

Every agent returns JSON conforming to one of these schemas. The orchestrator
validates the agent's output before persisting; if validation fails, it
retries with a correction prompt (max 2 retries).

These shapes are FUTURE-PROOFED to absorb the analysis checklist that
Ricardo will share on 2026-05-01: the `checklist_results: list[CheckItem]`
field is already there, we just need to seed `credit_analysis_item` rows
once the checklist arrives so the prompts can reference them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ─── Common building blocks ───────────────────────────────────────────────


class RedFlagItem(BaseModel):
    """A red flag detected during analysis."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["critical", "important", "informational"]
    title: str = Field(..., max_length=200)
    description: str
    evidence: str = Field(
        ...,
        description="Cite the source (document, bureau, agent output) backing this flag.",
    )


class CheckItem(BaseModel):
    """One checklist item evaluated by the agent."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., description="e.g. 'SOC.001', 'FIN.003'")
    description: str
    status: Literal["ok", "alert", "critical", "not_applicable"]
    rationale: str
    confidence: float = Field(..., ge=0.0, le=1.0)


# ─── Per-agent output schemas ─────────────────────────────────────────────


class SocialContractAnalysis(BaseModel):
    """Output of `social_contract_analyst`."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    qsa_changes_recent: bool = Field(
        ...,
        description="Houve alteracoes no quadro societario nos ultimos 24 meses?",
    )
    qsa_changes_detail: str | None = None
    signing_powers: dict[str, str] = Field(
        default_factory=dict,
        description="{socio_nome: 'isolada' | 'conjunta' | 'descricao'}",
    )
    object_compatible_with_operation: bool
    object_compatibility_rationale: str
    capital_social: dict = Field(
        default_factory=dict,
        description="{valor_brl: number, divisao: [{socio, pct}]}",
    )
    statutory_restrictions: list[str] = Field(default_factory=list)
    checklist_results: list[CheckItem] = Field(default_factory=list)
    red_flags: list[RedFlagItem] = Field(default_factory=list)


class FinancialAnalysis(BaseModel):
    """Output of `financial_analyst`."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    revenue_trend: Literal["growth", "stable", "decline", "volatile"]
    margin_evolution: dict = Field(
        default_factory=dict,
        description="By period: {periodo: {gross_margin, ebitda_margin, net_margin}}",
    )
    indicators: dict = Field(
        default_factory=dict,
        description="{ebitda_margin, current_ratio, debt_to_equity, ...}",
    )
    seasonality_detected: bool = False
    seasonality_pattern: str | None = None
    checklist_results: list[CheckItem] = Field(default_factory=list)
    red_flags: list[RedFlagItem] = Field(default_factory=list)


class IndebtednessAnalysis(BaseModel):
    """Output of `indebtedness_analyst`."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    total_debt_brl: float
    debt_concentration_top1_pct: float | None = None
    debt_concentration_top3_pct: float | None = None
    debt_to_revenue_pct: float | None = None
    short_term_vs_long_term: dict = Field(default_factory=dict)
    declared_vs_scr_consistency: Literal["consistent", "minor_diff", "major_diff", "unknown"]
    declared_vs_scr_diff_brl: float | None = None
    checklist_results: list[CheckItem] = Field(default_factory=list)
    red_flags: list[RedFlagItem] = Field(default_factory=list)


class LegalAnalysis(BaseModel):
    """Output of `legal_analyst`."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    judicial_processes_count: int
    judicial_processes_active: int
    judicial_processes_value_brl: float | None = None
    protests_count: int
    protests_value_brl: float | None = None
    risk_level: Literal["low", "medium", "high", "critical"]
    risk_rationale: str
    checklist_results: list[CheckItem] = Field(default_factory=list)
    red_flags: list[RedFlagItem] = Field(default_factory=list)


class PartnerAnalysis(BaseModel):
    """Output of `partner_analyst`."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    partners_evaluated: int
    aggregate_personal_patrimony_brl: float | None = None
    partners_with_restrictions: int = 0
    cross_relationships: list[str] = Field(
        default_factory=list,
        description="Connections between partners (kinship, common companies, etc).",
    )
    checklist_results: list[CheckItem] = Field(default_factory=list)
    red_flags: list[RedFlagItem] = Field(default_factory=list)


class CommercialVisitAnalysis(BaseModel):
    """Output of `commercial_visit_analyst`."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    visit_date: str | None = None
    facilities_consistent_with_declarations: bool
    declared_vs_observed_diff: list[str] = Field(default_factory=list)
    observations: str | None = None
    checklist_results: list[CheckItem] = Field(default_factory=list)
    red_flags: list[RedFlagItem] = Field(default_factory=list)


class CrossReferenceAnalysis(BaseModel):
    """Output of `cross_reference_analyst`."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    inconsistencies: list[dict] = Field(
        default_factory=list,
        description="{field, source_a, value_a, source_b, value_b, severity}",
    )
    confidence_level: Literal["high", "medium", "low"]
    red_flags: list[RedFlagItem] = Field(default_factory=list)


class OpinionDraft(BaseModel):
    """Output of `opinion_writer`."""

    model_config = ConfigDict(extra="forbid")

    executive_summary: str
    strengths: list[str]
    concerns: list[str]
    recommendation: Literal["approve", "deny", "conditional"]
    conditions: list[str] | None = None
    rationale: str


class DocumentExtraction(BaseModel):
    """Output of `document_extractor` — one extraction.

    The actual structured fields vary per document type; we keep the schema
    permissive (extra=allow) and the prompt for each type pins the shape.
    """

    model_config = ConfigDict(extra="allow")

    document_type: str
    extracted_fields: dict
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes: str | None = None


class PleitoExtraction(BaseModel):
    """Output of `pleito_extractor` — extracts pleito from informal text."""

    model_config = ConfigDict(extra="forbid")

    produto: str | None = None
    volume_brl: float | None = None
    taxa: str | None = None
    prazo: str | None = None
    contexto: str | None = None
    urgencia: Literal["alta", "media", "baixa"] | None = None
    confianca: float = Field(..., ge=0.0, le=1.0)
