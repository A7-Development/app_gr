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


# ─── Controladoria · analista variacao cota sub jr ───────────────────────


class SanityCheck(BaseModel):
    """Nivel 1 do agente — identidade contabil bateu no dia?"""

    model_config = ConfigDict(extra="forbid")

    passou: bool = Field(description="True se residuo_brl < tolerancia (R$ 1).")
    residuo_brl: float = Field(
        description="(ΔPL deduzido) − (ΔPL fonte MEC). Erro REAL do dia, nao "
                    "snapshot acumulado.",
    )
    pl_deduzido_delta: float = Field(description="Δ do PL calculado pelo granular.")
    pl_fonte_delta: float = Field(description="Δ do PL lido do MEC.")
    diagnostico: str = Field(
        description="Frase curta pt-BR: 'fechamento sadio' / 'arredondamento "
                    "centavos' / 'desalinhamento de pipeline'.",
    )


class CategoriaDelta(BaseModel):
    """Nivel 2 do agente — uma linha do balanco com ΔBRL."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Chave canonica: 'dc', 'pdd', 'cpr', etc.")
    label: str = Field(description="Label amigavel pt-BR.")
    tipo: Literal["ativo", "passivo"]
    d1: float
    d0: float
    delta: float = Field(description="d0 - d1 (sinal natural).")
    rank_magnitude: int = Field(
        ge=1,
        description="1 = maior |delta| do dia, 2 = segundo maior, etc.",
    )


class PapelMencionado(BaseModel):
    """Papel especifico citado pelo agente como evidencia."""

    model_config = ConfigDict(extra="forbid")

    seu_numero: str
    cedente_nome: str
    sacado_nome: str
    delta_brl: float = Field(description="Impacto do papel na categoria.")
    natureza: str = Field(
        description="ex.: 'mutacao_silenciosa', 'liquidacao_parcial', "
                    "'write_off', 'migracao_wop', 'aquisicao_novo'",
    )


class ExplicacaoCategoria(BaseModel):
    """Nivel 3 do agente — narrativa de uma categoria significativa."""

    model_config = ConfigDict(extra="forbid")

    categoria_key: str = Field(description="Match com CategoriaDelta.key.")
    narrativa: str = Field(
        description="Sintese pt-BR (2-5 frases) explicando o ΔBRL. "
                    "Concreto: cite papeis, cedentes, padroes temporais. "
                    "Evite vaguidade.",
    )
    papeis_mencionados: list[PapelMencionado] = Field(
        default_factory=list,
        description="Papeis especificos citados na narrativa.",
    )
    classificacao_principal: Literal[
        "carrego_normal",
        "fluxo_novo_intenso",
        "mutacao_silenciosa_pura",
        "padrao_abatimento_offrecord",
        "constituicao_pdd",
        "reversao_pdd",
        "aporte_engaiolado",
        "evento_pontual_explicado",
        "evento_pontual_sem_explicacao",
        "outro",
    ] = Field(description="Etiqueta canonica do que dominou a variacao.")
    confianca: float = Field(
        ge=0.0, le=1.0,
        description="Confianca da narrativa (0.5 = duas hipoteses; 0.95 = quase certo).",
    )


class SinalAlerta(BaseModel):
    """Sinal de risco detectado — concentracao, reincidencia, etc."""

    model_config = ConfigDict(extra="forbid")

    severidade: Literal["info", "atencao", "critico"]
    tipo: Literal[
        "cedente_reincidente",
        "sacado_problematico",
        "concentracao_categoria",
        "mutacao_silenciosa_material",
        "residuo_alto",
        "outro",
    ]
    entidade: str = Field(description="Nome do cedente/sacado/categoria envolvido.")
    descricao: str = Field(description="Frase pt-BR explicando o alerta.")
    evidencia: str = Field(description="Quais papeis/eventos suportam.")


class SugestaoAcao(BaseModel):
    """Acao recomendada ao controller."""

    model_config = ConfigDict(extra="forbid")

    prioridade: Literal["alta", "media", "baixa"]
    acao: str = Field(description="Verbo pt-BR: 'investigar', 'monitorar', 'nenhuma'.")
    detalhe: str = Field(description="O que fazer concretamente.")


class AnalysisVariacaoCotaResponse(BaseModel):
    """Output do agente `controladoria.analista_variacao_cota`.

    3 niveis (sanity + decomposicao + explicacao narrativa) + sinais de
    alerta + sugestoes de acao. UI consome cada bloco em uma secao distinta.
    """

    model_config = ConfigDict(extra="forbid")

    fundo_nome: str
    data: str = Field(description="ISO yyyy-mm-dd da data D0 analisada.")
    data_anterior: str = Field(description="ISO yyyy-mm-dd da data D-1.")

    nivel_1_sanity: SanityCheck
    nivel_2_decomposicao: list[CategoriaDelta] = Field(
        description="Todas as 12 categorias ordenadas por rank_magnitude ASC."
    )
    nivel_3_explicacoes: list[ExplicacaoCategoria] = Field(
        default_factory=list,
        description="Narrativas das categorias mais significativas (top N por "
                    "|delta| OU com pattern detectado).",
    )

    sinais_alerta: list[SinalAlerta] = Field(default_factory=list)
    sugestoes_acao: list[SugestaoAcao] = Field(default_factory=list)

    sumario_executivo: str = Field(
        description="2-4 frases pt-BR resumindo a variacao do dia. "
                    "Headline pra controller que so vai ler isso.",
    )
