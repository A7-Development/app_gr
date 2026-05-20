"""Catalog of Specialist Agents available in the workflow engine.

Each entry in `CATALOG` maps an agent name to a `SpecialistAgentSpec` that
fully describes how the agent runs:
- Which prompt (versioned in `ai_prompt`)
- Which tools it can call (subset of `app.agentic.engine.tools`)
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

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.agentic.engine.output_schemas import (
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
from app.shared.workflow.nodes._base import VarType

if TYPE_CHECKING:
    pass


@dataclass(frozen=True, slots=True)
class AgentInput:
    """One typed input slot the agent expects to receive at runtime.

    Each slot is filled at graph construction time via
    `node.config.input_bindings = {name: "node.X.output.Y"}`. The runtime
    resolves each ref and packages the values as a NAMED, STRUCTURED JSON
    object delivered to the LLM — no truncation, no JSON dump of unrelated
    upstream nodes.

    When `inputs` is empty (default), the agent falls back to the legacy
    behavior: full `previous_outputs` dumped as text, truncated at 2000
    chars/node. This back-compat keeps existing graphs working until each
    agent is migrated.
    """

    name: str
    type: VarType
    description: str = ""
    optional: bool = False


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
    # Declared input contract — when non-empty, the runtime delivers a
    # structured JSON of these slots (resolved via `config.input_bindings`)
    # to the LLM, instead of dumping all `previous_outputs` as truncated
    # text. Empty tuple = legacy fallback path (back-compat).
    inputs: tuple[AgentInput, ...] = field(default_factory=tuple)


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
        # Primeira migracao para o caminho de contexto estruturado
        # (ver runtime._render_context_for_prompt). Cada slot e ligado
        # a um ref upstream em `node.config.input_bindings` no graph.
        inputs=(
            AgentInput(
                name="cnpj",
                type=VarType.CNPJ,
                description="CNPJ da empresa analisada.",
            ),
            AgentInput(
                name="score_pj",
                type=VarType.SCORE,
                description="Score de credito PJ mais recente (Serasa ou bureau equivalente).",
                optional=True,
            ),
            AgentInput(
                name="endividamento_total",
                type=VarType.MONEY_BRL,
                description="Endividamento bancario consolidado em BRL (de bureau ou SCR).",
                optional=True,
            ),
            AgentInput(
                name="ebitda",
                type=VarType.MONEY_BRL,
                description="EBITDA do ultimo periodo extraido do balanco.",
                optional=True,
            ),
        ),
    ),
    "indebtedness_analyst": SpecialistAgentSpec(
        name="indebtedness_analyst",
        description="Analisa SCR + dividas declaradas; concentracao bancaria.",
        prompt_name="agent.indebtedness",
        tools=(TOOL_DOSSIER_READ, TOOL_DOC_GET, TOOL_REF_COMPARE, TOOL_DOSSIER_FLAG, TOOL_DOSSIER_SAVE),
        output_schema=IndebtednessAnalysis,
        thinking_budget_tokens=10000,
        section_id="indebtedness",
        inputs=(
            AgentInput(
                name="cnpj",
                type=VarType.CNPJ,
                description="CNPJ da empresa analisada.",
            ),
            AgentInput(
                name="endividamento_total_brl",
                type=VarType.MONEY_BRL,
                description="Endividamento total consolidado em BRL (de bureau ou SCR).",
                optional=True,
            ),
            AgentInput(
                name="scr_carteira_ativa_brl",
                type=VarType.MONEY_BRL,
                description="Carteira ativa no SCR Bacen — operacoes em curso.",
                optional=True,
            ),
            AgentInput(
                name="qtd_instituicoes_relacionamento",
                type=VarType.NUMBER,
                description="Numero de instituicoes financeiras com relacionamento ativo (concentracao).",
                optional=True,
            ),
        ),
    ),
    "legal_analyst": SpecialistAgentSpec(
        name="legal_analyst",
        description="Analisa processos judiciais e protestos; classifica risco juridico.",
        prompt_name="agent.legal",
        tools=(TOOL_DOSSIER_READ, TOOL_DOSSIER_FLAG, TOOL_DOSSIER_SAVE),
        output_schema=LegalAnalysis,
        thinking_budget_tokens=10000,
        section_id="legal",
        inputs=(
            AgentInput(
                name="cnpj",
                type=VarType.CNPJ,
                description="CNPJ da empresa analisada.",
            ),
            AgentInput(
                name="processos_total_qtd",
                type=VarType.NUMBER,
                description="Quantidade total de processos judiciais (ativos + arquivados).",
                optional=True,
            ),
            AgentInput(
                name="processos_ativos_valor_brl",
                type=VarType.MONEY_BRL,
                description="Valor total em disputa nos processos ativos, em BRL.",
                optional=True,
            ),
            AgentInput(
                name="protestos_ativos_qtd",
                type=VarType.NUMBER,
                description="Quantidade de protestos cartoriais ativos (CENPROT).",
                optional=True,
            ),
        ),
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
        # Synthesizer agent — slots sao outputs de outros specialist agents
        # upstream. Tipicamente ligados a financial_analyst.summary,
        # legal_analyst.red_flags, etc.
        inputs=(
            AgentInput(
                name="cnpj",
                type=VarType.CNPJ,
                description="CNPJ da empresa analisada (ancora a analise).",
            ),
            AgentInput(
                name="financial_summary",
                type=VarType.STRING,
                description="Resumo da analise financeira (financial_analyst.output.summary).",
                optional=True,
            ),
            AgentInput(
                name="financial_red_flags",
                type=VarType.LIST,
                description="Red flags financeiros (financial_analyst.output.red_flags).",
                optional=True,
            ),
            AgentInput(
                name="legal_summary",
                type=VarType.STRING,
                description="Resumo da analise juridica (legal_analyst.output.summary).",
                optional=True,
            ),
            AgentInput(
                name="legal_red_flags",
                type=VarType.LIST,
                description="Red flags juridicos (legal_analyst.output.red_flags).",
                optional=True,
            ),
            AgentInput(
                name="social_contract_red_flags",
                type=VarType.LIST,
                description="Red flags do contrato social (social_contract_analyst.output.red_flags).",
                optional=True,
            ),
            AgentInput(
                name="partner_summary",
                type=VarType.STRING,
                description="Resumo da analise de socios (partner_analyst.output.summary).",
                optional=True,
            ),
        ),
    ),
    "opinion_writer": SpecialistAgentSpec(
        name="opinion_writer",
        description="Gera parecer consolidado com recomendacao final.",
        prompt_name="agent.opinion",
        tools=(TOOL_DOSSIER_READ,),
        output_schema=OpinionDraft,
        # 8k thinking + 4k headroom -> 12k max_tokens. Mantem abaixo do
        # threshold do Anthropic SDK que exige stream=True (~24k em Sonnet/
        # Opus 4.5). Para parecer (~600-1500 palavras + raciocinio interno)
        # 8k de thinking budget e folgado. Se virar gargalo, migrar runtime
        # para messages.stream() -- refactor de _run_tool_loop.
        thinking_budget_tokens=8000,
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
