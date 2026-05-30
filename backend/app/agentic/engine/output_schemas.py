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


# Redesign 2026-05-29 (renovacao total): output organizado pra leitura em
# segundos — macro (Ativo vs Passivo -> PL Sub) -> ofensores (bullets 5s) ->
# grupos na ordem da tabela (Ativos -> Passivos, bullets primeiro + explicacao
# depois) -> conclusao + alertas. O coracao e o flag `atipico`: separa o
# movimento que merece atencao do grande-porem-normal. A regua de calculo/sinal
# vive nas TOOLS (engrossadas) — o agente le campos prontos e narra.


class AtipicidadeFlag(BaseModel):
    """Marca um movimento como atipico (merece atencao) + por que."""

    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(description="Por que e atipico, 1 frase concreta.")
    severidade: Literal["info", "atencao", "critico"]


class SanityMacro(BaseModel):
    """Resumo do Nivel 1 (vem pronto de check_identidade_contabil)."""

    model_config = ConfigDict(extra="forbid")

    severidade: Literal["ok", "atencao", "critico"]
    residuo_brl: float = Field(description="(ΔPL deduzido) - (ΔPL fonte MEC).")
    deve_continuar: bool = Field(
        description="False so em residuo critico (>= R$ 5.000) — ai a analise para.",
    )


class MacroVariacao(BaseModel):
    """Bloco macro — o fundamento: ΔPL Sub = ΔAtivo - ΔPassivo."""

    model_config = ConfigDict(extra="forbid")

    pl_sub_d1: float
    pl_sub_d0: float
    pl_sub_delta: float = Field(description="Variacao do PL Sub Jr no dia (d0 - d1).")
    total_ativo_delta: float = Field(description="Δ do total de ativos.")
    total_passivo_delta: float = Field(description="Δ do total de passivos.")
    leitura: str = Field(
        description="1 frase: como ativo e passivo compuseram o ΔPL Sub "
                    "(ex.: 'PL Sub +X: ativos renderam +A e passivos cairam -P').",
    )
    sanity: SanityMacro


class OfensorLinha(BaseModel):
    """Top mover do dia por impacto no PL Sub — leitura em 5 segundos."""

    model_config = ConfigDict(extra="forbid")

    lado: Literal["ativo", "passivo"]
    key: str = Field(description="Chave da linha do balanco (dc_bruto, pdd, cpr_pagar, ...).")
    label: str
    delta: float = Field(description="Δ natural da linha (d0 - d1).")
    impacto_pl_sub: float = Field(
        description="Impacto no PL Sub com sinal corrigido (positivo ajudou a cota).",
    )
    atipico: bool = Field(description="True quando este movimento foge do normal.")
    bullet: str = Field(description="1 linha factual, leitura em 5s.")


class PapelMencionado(BaseModel):
    """Papel especifico citado pelo agente como evidencia."""

    model_config = ConfigDict(extra="forbid")

    seu_numero: str
    numero_documento: str = Field(
        default="",
        description="Numero do documento/titulo (ex.: '39805'). PREFERIR este na "
                    "narrativa e na UI em vez do seu_numero/DID.",
    )
    cedente_nome: str
    sacado_nome: str
    delta_brl: float = Field(description="Impacto do papel na linha.")
    natureza: str = Field(
        description="ex.: 'mutacao_silenciosa', 'apropriacao_antecipada', 'juros_mora', "
                    "'desconto_concedido', 'write_off', 'migracao_wop', "
                    "'aquisicao_novo', 'efeito_vagao'",
    )


class GrupoAnalise(BaseModel):
    """Analise de uma linha do balanco. Bullets primeiro, profundidade depois."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Chave da linha (dc_bruto, pdd, cpr_pagar, senior, ...).")
    label: str
    lado: Literal["ativo", "passivo"]
    d1: float
    d0: float
    delta: float = Field(description="d0 - d1 (sinal natural).")
    impacto_pl_sub: float = Field(description="Impacto no PL Sub (sinal corrigido).")
    atipico: bool = Field(description="True quando o movimento merece atencao.")
    atipicidade: AtipicidadeFlag | None = Field(
        default=None,
        description="Preenchido quando atipico=True; null quando normal.",
    )
    classificacao: str | None = Field(
        default=None,
        description="Etiqueta do que dominou (vem da sugestao da tool: carrego_normal, "
                    "evento_pontual_explicado, constituicao_pdd, aporte_classe, etc.).",
    )
    bullets: list[str] = Field(
        default_factory=list,
        description="2-4 pontos curtos, leitura rapida — VEM PRIMEIRO na UI.",
    )
    explicacao: str = Field(
        description="1-3 frases de profundidade, DEPOIS dos bullets. So aprofunde "
                    "onde importa; linha normal pode ter explicacao minima.",
    )
    papeis: list[PapelMencionado] = Field(
        default_factory=list,
        description="Papeis especificos citados, quando relevante.",
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


class AnalysisVariacaoCotaResponse(BaseModel):
    """Output do agente `controladoria.analista_variacao_cota` (redesign 2026-05-29).

    Leitura em camadas: macro (Ativo vs Passivo) -> ofensores (bullets 5s) ->
    grupos por linha do balanco (Ativos depois Passivos) -> conclusao. Alertas
    carregam os atipicos materiais (auditabilidade §14).
    """

    model_config = ConfigDict(extra="forbid")

    fundo_nome: str
    data: str = Field(description="ISO yyyy-mm-dd da data D0 analisada.")
    data_anterior: str = Field(description="ISO yyyy-mm-dd da data D-1.")

    macro: MacroVariacao
    ofensores: list[OfensorLinha] = Field(
        default_factory=list,
        description="Top ~5 movers por |impacto_pl_sub|, ativos e passivos juntos.",
    )
    grupos: list[GrupoAnalise] = Field(
        default_factory=list,
        description="1 por linha do balanco com movimento relevante, na ordem da "
                    "tabela: Ativos (DC, PDD, ...) depois Passivos.",
    )
    conclusao: str = Field(
        description="Fecho curto (1-3 frases) — o que o controller leva do dia.",
    )
    alertas: list[SinalAlerta] = Field(
        default_factory=list,
        description="So os atipicos materiais que merecem registro/acao.",
    )
