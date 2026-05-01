"""Catalog of Specialist Agents available in the workflow engine.

Each entry in `CATALOG` maps an agent name to a `SpecialistAgentSpec` that
fully describes how the agent runs:
- Which prompt (versioned in `ai_prompt`)
- Which tools it can call (subset of `app.shared.agents.tools`)
- Which Pydantic schema validates its output
- Model preference, thinking budget, timeout

Adding a new agent:
1. Define output schema in `output_schemas.py`
2. Add `extract.<name>` or `agent.<name>` prompt seed (Alembic migration
   that inserts into `ai_prompt` + `ai_prompt_active`)
3. Register here

This is a code-defined catalog (vs DB-defined like `ai_prompt`) because
the OUTPUT SCHEMA is a Pydantic class — it must match the orchestrator's
parsing logic. The prompt itself is editable via DB (no deploy needed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.shared.agents.output_schemas import (
    CommercialVisitAnalysis,
    CrossReferenceAnalysis,
    DocumentExtraction,
    FinancialAnalysis,
    IndebtednessAnalysis,
    LegalAnalysis,
    OpinionDraft,
    PartnerAnalysis,
    PleitoExtraction,
    SocialContractAnalysis,
)

if TYPE_CHECKING:
    pass


@dataclass(frozen=True, slots=True)
class SpecialistAgentSpec:
    """Static spec for a specialist agent."""

    name: str
    description: str
    prompt_name: str  # ref to `ai_prompt.name` (resolved via repository)
    tools: tuple[str, ...]
    output_schema: type
    preferred_model: str = "claude-opus-4-5"
    fallback_model: str | None = "claude-sonnet-4-5"
    thinking_budget_tokens: int = 10000
    timeout_seconds: int = 300
    # When True, this agent is multimodal (accepts images/PDFs as input).
    multimodal: bool = False
    # Per-section affinity — used by the UI to associate agent output to
    # a tab in the dossier view. Free-form string keyed to the dossier UI.
    section_id: str = ""


# ─── Tools available to specialist agents ─────────────────────────────────
# Names map to factories in `app/shared/agents/tools/`. The runtime
# instantiates only the requested subset for each agent run.

TOOL_DOSSIER_READ = "read_dossier_section"
TOOL_DOSSIER_FLAG = "flag_red_flag"
TOOL_DOSSIER_SAVE = "save_analysis"
TOOL_DOC_GET = "get_document_extraction"
TOOL_DOC_LIST = "list_documents_in_section"
TOOL_REF_COMPARE = "compare_values"
TOOL_REF_CALC = "calculate_metric"


# ─── The catalog ─────────────────────────────────────────────────────────


CATALOG: dict[str, SpecialistAgentSpec] = {
    "social_contract_analyst": SpecialistAgentSpec(
        name="social_contract_analyst",
        description="Analisa contrato social: firmas, poderes, alteracoes QSA, objeto.",
        prompt_name="agent.social_contract",
        tools=(TOOL_DOSSIER_READ, TOOL_DOC_GET, TOOL_DOSSIER_FLAG, TOOL_DOSSIER_SAVE),
        output_schema=SocialContractAnalysis,
        thinking_budget_tokens=15000,
        section_id="social_contract",
    ),
    "financial_analyst": SpecialistAgentSpec(
        name="financial_analyst",
        description="Analisa DRE+Balanco+Faturamento; calcula indicadores e tendencias.",
        prompt_name="agent.financial",
        tools=(
            TOOL_DOSSIER_READ,
            TOOL_DOC_GET,
            TOOL_REF_CALC,
            TOOL_DOSSIER_FLAG,
            TOOL_DOSSIER_SAVE,
        ),
        output_schema=FinancialAnalysis,
        thinking_budget_tokens=15000,
        section_id="financial",
    ),
    "indebtedness_analyst": SpecialistAgentSpec(
        name="indebtedness_analyst",
        description="Analisa SCR + dividas declaradas; concentracao bancaria.",
        prompt_name="agent.indebtedness",
        tools=(TOOL_DOSSIER_READ, TOOL_DOC_GET, TOOL_REF_COMPARE, TOOL_DOSSIER_FLAG, TOOL_DOSSIER_SAVE),
        output_schema=IndebtednessAnalysis,
        thinking_budget_tokens=10000,
        section_id="indebtedness",
    ),
    "legal_analyst": SpecialistAgentSpec(
        name="legal_analyst",
        description="Analisa processos judiciais e protestos; classifica risco juridico.",
        prompt_name="agent.legal",
        tools=(TOOL_DOSSIER_READ, TOOL_DOSSIER_FLAG, TOOL_DOSSIER_SAVE),
        output_schema=LegalAnalysis,
        thinking_budget_tokens=10000,
        section_id="legal",
    ),
    "partner_analyst": SpecialistAgentSpec(
        name="partner_analyst",
        description="Analisa socios e representantes (patrimonio, processos, ligacoes).",
        prompt_name="agent.partners",
        tools=(TOOL_DOSSIER_READ, TOOL_DOC_GET, TOOL_DOSSIER_FLAG, TOOL_DOSSIER_SAVE),
        output_schema=PartnerAnalysis,
        thinking_budget_tokens=10000,
        section_id="partners",
    ),
    "commercial_visit_analyst": SpecialistAgentSpec(
        name="commercial_visit_analyst",
        description="Analisa relatorio de visita; consistencia com declaracoes.",
        prompt_name="agent.commercial_visit",
        tools=(TOOL_DOSSIER_READ, TOOL_DOC_GET, TOOL_DOSSIER_FLAG, TOOL_DOSSIER_SAVE),
        output_schema=CommercialVisitAnalysis,
        thinking_budget_tokens=8000,
        section_id="commercial_visit",
    ),
    "cross_reference_analyst": SpecialistAgentSpec(
        name="cross_reference_analyst",
        description="Cruza dados de TODAS as secoes para detectar inconsistencias.",
        prompt_name="agent.cross_reference",
        tools=(TOOL_DOSSIER_READ, TOOL_REF_COMPARE, TOOL_DOSSIER_FLAG),
        output_schema=CrossReferenceAnalysis,
        thinking_budget_tokens=20000,
        section_id="cross_reference",
    ),
    "opinion_writer": SpecialistAgentSpec(
        name="opinion_writer",
        description="Gera parecer consolidado com recomendacao final.",
        prompt_name="agent.opinion",
        tools=(TOOL_DOSSIER_READ,),
        output_schema=OpinionDraft,
        thinking_budget_tokens=20000,
        section_id="opinion",
    ),
    "document_extractor": SpecialistAgentSpec(
        name="document_extractor",
        description="Extrai dados estruturados de documentos via Claude Vision multimodal.",
        prompt_name="extract.document",  # base — runtime swaps to extract.<doc_type>
        tools=(),  # no tools — single-shot extraction
        output_schema=DocumentExtraction,
        thinking_budget_tokens=5000,
        timeout_seconds=180,
        multimodal=True,
        section_id="documents",
    ),
    "pleito_extractor": SpecialistAgentSpec(
        name="pleito_extractor",
        description="Extrai campos do pleito de email/texto informal do comercial.",
        prompt_name="extract.pleito_informal",
        tools=(),
        output_schema=PleitoExtraction,
        preferred_model="claude-haiku-4-5-20251001",
        thinking_budget_tokens=2000,
        timeout_seconds=60,
        section_id="plea",
    ),
}
