"""Catalog of Specialist Agents available in the workflow engine.

Each entry in `CATALOG` maps an agent name to a `SpecialistAgentSpec` that
fully describes how the agent runs:
- Which prompt (versioned in `ai_prompt`)
- Which tools it can call (subset of `app.agentic.tools` registered via `@register_tool`)
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
    AnalysisVariacaoCotaResponse,
    AuditoriaNotaComercialResponse,
    AuditoriaPddResponse,
    AuditoriaResultadoResponse,
    AuditoriaVariacaoCaixaResponse,
    AuditoriaVariacaoCarteiraResponse,
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
from app.agentic.playbooks.nodes._base import VarType

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
    # ─── Controladoria · analista de variacao da Cota Sub Jr ─────────────
    # Retomada de [[project_pagina_variacao_cota]] em 2026-05-24 apos
    # F1+F2+F5 do redesign cota-sub serem entregues (PR #26 mergeado em
    # main). 3 niveis de analise (sanity + decomposicao + explicacao
    # narrativa). Consome as 8 tools de app/agentic/tools/controladoria/.
    "analista_variacao_cota": SpecialistAgentSpec(
        name="analista_variacao_cota",
        description=(
            "Explica narrativamente a variacao do PL Sub Jr de um FIDC entre "
            "D-1 e D0. Faz sanity check, decompoe nas 12 categorias do "
            "balanco, e investiga categorias com Δ material cruzando "
            "wh_estoque_recebivel x wh_liquidacao_recebivel x historico do "
            "papel pra distinguir liquidacao normal, mutacao silenciosa pura, "
            "padrao de abatimento off-record, etc."
        ),
        prompt_name="agent.controladoria.analista_variacao_cota",
        tools=(
            "check_identidade_contabil",
            "get_balanco_patrimonial",
            "get_variacao_carteira",
            "get_drill_pdd",
            "get_drill_cpr",
            "get_decomposicao_classes",
            "get_eventos_liquidacao_adjacentes",
            "get_historico_estoque_papel",
            "get_papeis_mesmo_cedente_sacado",
        ),
        output_schema=AnalysisVariacaoCotaResponse,
        # Modelo Opus 4.7 escolhido pra narrativa rica + raciocinio em
        # padroes temporais. Cache de prompt resolve custo (system_text
        # estavel cross-runs).
        preferred_model="claude-opus-4-7",
        fallback_model="claude-sonnet-4-6",
        thinking_budget_tokens=15000,
        timeout_seconds=600,
        section_id="cota_sub_analise_variacao",
    ),
    # ─── Controladoria · auditor de variacao de CARTEIRA (DC) ────────────
    # Especialista (2026-05-30): segmentacao do monolito. Audita SO a
    # consistencia da variacao do estoque DC (decomposicao D-1 vs D0) — 1 tool.
    # Conciliacao de caixa = outro agente (auditor_variacao_caixa).
    "auditor_variacao_carteira": SpecialistAgentSpec(
        name="auditor_variacao_carteira",
        description=(
            "Audita a consistencia da variacao da carteira de Direitos "
            "Creditorios (DC) entre D-1 e D0: decompoe o ΔDC em 5 motores "
            "(aquisicoes, liquidacoes, migracao WOP, apropriacao, mutacao), "
            "separa rotina de atipico, detalha apropriacao (normal vs "
            "antecipada) e da o selo de fechamento. NAO julga credito nem "
            "concilia caixa."
        ),
        prompt_name="agent.controladoria.auditor_variacao_carteira",
        tools=("get_variacao_carteira",),
        output_schema=AuditoriaVariacaoCarteiraResponse,
        preferred_model="claude-opus-4-7",
        fallback_model="claude-sonnet-4-6",
        thinking_budget_tokens=8000,
        timeout_seconds=300,
        section_id="auditor_variacao_carteira",
    ),
    # ─── Controladoria · auditor de RESULTADO (renda/P&L da carteira) ────
    # Especialista (2026-05-30): lente de P&L. Le SO o bloco resultado_do_dia
    # da tool get_variacao_carteira (renda: carrego, antecipada, mora, desconto).
    # Espelho do Auditor de Variacao de Carteira, na lente de resultado.
    "auditor_resultado": SpecialistAgentSpec(
        name="auditor_resultado",
        description=(
            "Audita o RESULTADO/renda da carteira de Direitos Creditorios no "
            "dia: separa renda CONTRATADA (apropriacao normal + antecipada — "
            "ja na curva) da EXTRA (juros de mora, por atraso) e da PERDA "
            "(desconto). Detalha apropriacao normal vs antecipada. NAO audita "
            "o estoque nem o caixa."
        ),
        prompt_name="agent.controladoria.auditor_resultado",
        tools=("get_variacao_carteira",),
        output_schema=AuditoriaResultadoResponse,
        preferred_model="claude-opus-4-7",
        fallback_model="claude-sonnet-4-6",
        thinking_budget_tokens=8000,
        timeout_seconds=300,
        section_id="auditor_resultado",
    ),
    # ─── Controladoria · auditor de PROVISAO/PDD ────────────────────────
    # Especialista (2026-05-30): lente de provisao. Le get_drill_pdd. Separa
    # PDD propria (titulo vencido) de PDD por arrasto (efeito vagao), nas duas
    # direcoes (constituicao forward / reversao por liberacao).
    "auditor_pdd": SpecialistAgentSpec(
        name="auditor_pdd",
        description=(
            "Audita a variacao da PROVISAO (PDD) da carteira no dia: separa "
            "constituicao PROPRIA (titulo vencido) de constituicao por ARRASTO "
            "(efeito vagao — puxador arrasta os a-vencer), e reversao por "
            "LIQUIDACAO (titulo proprio pagou) de reversao por LIBERACAO (vagao "
            "reverso — puxador liquidou e soltou os a-vencer). NAO audita "
            "estoque, renda nem caixa."
        ),
        prompt_name="agent.controladoria.auditor_pdd",
        tools=("get_drill_pdd",),
        output_schema=AuditoriaPddResponse,
        preferred_model="claude-opus-4-7",
        fallback_model="claude-sonnet-4-6",
        thinking_budget_tokens=8000,
        timeout_seconds=300,
        section_id="auditor_pdd",
    ),
    # ─── Controladoria · auditor de VARIACAO DE CAIXA (fluxo de caixa) ───
    # Especialista (2026-05-31): lente de FLUXO. Confere a ENTRADA (liquidacao)
    # e a SAIDA (cessao) de caixa do dia. Floating NORMAL+CARTÓRIO -> PROV(d+1
    # util) casa por lote; deposito sacado = imediato/agregado; cessao = TED
    # exata ao cedente. Direcao point-in-time: confere PRA TRAS (caixa que caiu
    # hoje <- origem). NAO audita estoque, renda nem provisao.
    "auditor_variacao_caixa": SpecialistAgentSpec(
        name="auditor_variacao_caixa",
        description=(
            "Audita o FLUXO DE CAIXA do dia: ENTRADA por liquidacao (floating "
            "NORMAL+CARTÓRIO que pingou no PROV de hoje, casado por lote ao "
            "dia-origem; deposito sacado imediato/agregado; honra do cedente) e "
            "SAIDA por cessao (TED exata ao cedente). Confere PRA TRAS (caixa que "
            "caiu hoje <- origem). NAO audita estoque, renda nem provisao."
        ),
        prompt_name="agent.controladoria.auditor_variacao_caixa",
        tools=("get_conferencia_liquidacao", "get_conferencia_cessao"),
        output_schema=AuditoriaVariacaoCaixaResponse,
        preferred_model="claude-opus-4-7",
        fallback_model="claude-sonnet-4-6",
        thinking_budget_tokens=8000,
        timeout_seconds=300,
        section_id="auditor_variacao_caixa",
    ),
    # ─── Controladoria · auditor de NOTAS COMERCIAIS (Op. Estruturadas) ──
    # Especialista (2026-05-31): lente da linha "Op. Estruturadas" do balanco
    # (= Notas Comerciais, papeis NCPX/VCNC/PDDNC). POSICAO-FIRST: a posicao
    # manda; a amortizacao reduz valor_bruto (nao some); o extrato so confirma
    # valor (liquidacao da NC = transferencia interna do fundo). NAO audita DC,
    # caixa, renda nem provisao.
    "auditor_notas_comerciais": SpecialistAgentSpec(
        name="auditor_notas_comerciais",
        description=(
            "Audita a linha 'Op. Estruturadas' do balanco (= Notas Comerciais): "
            "abre o ΔSaldo em aquisicao (codigo novo, caixa saiu) | amortizacao "
            "(valor_bruto cai em parcela) | quitacao (zerou) | apropriacao "
            "(carrego). POSICAO-FIRST — a posicao manda, o extrato so confirma "
            "valor (a liquidacao da NC e transferencia interna do fundo). NAO "
            "audita DC, caixa, renda nem provisao."
        ),
        prompt_name="agent.controladoria.auditor_notas_comerciais",
        tools=("get_movimento_nota_comercial",),
        output_schema=AuditoriaNotaComercialResponse,
        preferred_model="claude-opus-4-7",
        fallback_model="claude-sonnet-4-6",
        thinking_budget_tokens=8000,
        timeout_seconds=300,
        section_id="auditor_notas_comerciais",
    ),
}
