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


# ─── Auditor de Variacao de Carteira (DC) — especialista 2026-05-30 ────────
#
# Audita a CONSISTENCIA da variacao da carteira de Direitos Creditorios (DC)
# entre D-1 e D0: o que moveu o estoque, separa atipico de rotina, da o selo
# de fechamento. NAO julga qualidade de credito; NAO concilia caixa (isso e o
# Auditor de Variacao de Caixa). Le SO a tool get_variacao_carteira.


class MotorCarteira(BaseModel):
    """Um motor da variacao do ESTOQUE DC no dia (os 5 buckets que fecham)."""

    model_config = ConfigDict(extra="forbid")

    key: Literal[
        "aquisicoes", "liquidacoes", "migracao_wop", "apropriacao", "mutacao"
    ]
    label: str
    valor: float = Field(description="Impacto no estoque DC (R$, com sinal natural).")
    natureza: Literal["rotina", "atencao"] = Field(
        description="rotina = movimento esperado (carrego, giro); atencao = foge do padrao."
    )
    bullet: str = Field(description="1 linha factual, leitura 5s, ancorada em R$.")


class ConsistenciaCarteira(BaseModel):
    """Selo de fechamento da decomposicao — a assinatura do auditor."""

    model_config = ConfigDict(extra="forbid")

    fecha: bool = Field(
        description="True quando a decomposicao bate o estoque D0 (residuo dentro da tolerancia)."
    )
    residuo: float = Field(description="saldo_d0 - (saldo_d1 + Σ motores). R$.")
    nota: str = Field(
        description="'Fecha por construcao' OU, se nao fecha, 'residuo R$ X — "
                    "desalinhamento de pipeline (nao e erro do fundo)'."
    )


class PontoAtencaoCarteira(BaseModel):
    """Um movimento atipico no estoque DC que merece atencao."""

    model_config = ConfigDict(extra="forbid")

    severidade: Literal["info", "atencao", "critico"]
    tipo: Literal[
        "mutacao_silenciosa", "apropriacao_anormal", "write_off",
        "liquidacao_atipica", "outro",
    ]
    titulo: str = Field(description="Headline curto do ponto de atencao (1 frase).")
    descricao: str
    evidencia: str = Field(
        description="Cite o papel por numero_documento (NUNCA o DID/seu_numero) + valores R$."
    )


class AuditoriaVariacaoCarteiraResponse(BaseModel):
    """Output do agente `controladoria.auditor_variacao_carteira` (2026-05-30).

    Lente da DECOMPOSICAO do estoque DC: a carteira variou de saldo_d1 -> saldo_d0
    por 5 motores (aquisicoes, liquidacoes, migracao WOP, apropriacao, mutacao),
    que FECHAM por construcao. O auditor separa rotina de atipico, detalha a
    apropriacao (normal vs antecipada) e da o selo de consistencia.
    """

    model_config = ConfigDict(extra="forbid")

    fundo_nome: str
    data: str = Field(description="ISO yyyy-mm-dd da data D0 analisada.")
    data_anterior: str = Field(description="ISO yyyy-mm-dd da data D-1.")

    resumo: str = Field(
        description="Leitura 5s: a carteira variou R$ X, fecha?, motor dominante, ha atipico?"
    )

    saldo_d1: float = Field(description="Σ VP do estoque ex-WOP em D-1. R$.")
    saldo_d0: float = Field(description="Σ VP do estoque ex-WOP em D0. R$.")
    delta: float = Field(description="saldo_d0 - saldo_d1. R$.")

    motores: list[MotorCarteira] = Field(
        default_factory=list,
        description="Os 5 motores do estoque com movimento relevante (pule ~0).",
    )
    consistencia: ConsistenciaCarteira
    atencao: list[PontoAtencaoCarteira] = Field(
        default_factory=list,
        description="So os movimentos atipicos. Dia limpo = [].",
    )
    conclusao: str = Field(
        description="1-3 frases: o que o controller leva do dia (destaca o atipico).",
    )


# ─── Auditor de Resultado (renda/P&L da carteira) — especialista 2026-05-30 ──
#
# Lente de RESULTADO/P&L: o que a carteira RENDEU no dia. Le SO o bloco
# resultado_do_dia da tool get_variacao_carteira. Separa 3 naturezas:
# CONTRATADA (carrego + antecipada), EXTRA (juros de mora), PERDA (desconto).
# NAO audita o estoque (= Auditor de Variacao de Carteira) nem caixa.


class ComponenteRenda(BaseModel):
    """Um componente da renda do dia, com a natureza explicita."""

    model_config = ConfigDict(extra="forbid")

    key: Literal[
        "apropriacao_normal", "apropriacao_antecipada", "juros_mora", "desconto"
    ]
    label: str
    valor: float = Field(
        description="R$. Apropriacao e mora positivos (renda); desconto = magnitude da perda."
    )
    natureza: Literal["contratada", "extra", "perda"] = Field(
        description="contratada = carrego/antecipada (ja na curva); extra = mora (atraso); perda = desconto."
    )
    bullet: str = Field(description="1 linha factual, ancorada em R$.")


class DestaqueRenda(BaseModel):
    """Concentracao/destaque na renda (ex.: mora num par cedente/sacado)."""

    model_config = ConfigDict(extra="forbid")

    descricao: str
    evidencia: str = Field(
        description="Cite por numero_documento (NUNCA o DID/seu_numero) + valores R$."
    )


class AuditoriaResultadoResponse(BaseModel):
    """Output do agente `controladoria.auditor_resultado` (2026-05-30).

    Lente de RESULTADO/P&L: o que a carteira RENDEU no dia, separando renda
    CONTRATADA (apropriacao normal + antecipada — ja na curva, NAO extra) da
    renda EXTRA (juros de mora, por atraso) e da PERDA (desconto). NAO audita
    o estoque (Auditor de Variacao de Carteira) nem o caixa.
    """

    model_config = ConfigDict(extra="forbid")

    fundo_nome: str
    data: str = Field(description="ISO yyyy-mm-dd da data D0 analisada.")
    data_anterior: str = Field(description="ISO yyyy-mm-dd da data D-1.")

    resumo: str = Field(
        description="Leitura 5s: a carteira rendeu R$ X — quanto contratada (carrego+antecipada) "
                    "vs extra (mora) vs perda (desconto)."
    )

    apropriacao_contratada: float = Field(
        description="apropriacao_normal + apropriacao_antecipada (renda ja contratada na curva). R$."
    )
    resultado_liquido: float = Field(
        description="apropriacao_contratada + juros_mora - desconto (resultado da renda no dia). R$."
    )

    componentes: list[ComponenteRenda] = Field(
        default_factory=list,
        description="Componentes da renda com valor relevante (pule ~0). Apropriacao normal e "
                    "antecipada SEMPRE separadas — a antecipada NAO e receita extra.",
    )
    destaques: list[DestaqueRenda] = Field(
        default_factory=list,
        description="Concentracoes/destaques (ex.: mora concentrada num par cedente/sacado). "
                    "Mora e renda NORMAL, nao anomalia — so destaque informativo.",
    )
    conclusao: str = Field(
        description="1-3 frases: o que rendeu o dia e a composicao (contratada vs extra vs perda)."
    )


# ─── Auditor de Provisao/PDD — especialista 2026-05-30 ─────────────────────
#
# Lente de PROVISAO (contra-ativo): por que a PDD ex-WOP mexeu entre D-1 e D0.
# A pegadinha: PDD nasce do titulo VENCIDO do sacado, mas ARRASTA os demais
# titulos do mesmo sacado (efeito vagao). Auditor separa PDD PROPRIA (titulo
# vencido) de PDD por ARRASTO (puxado por irmao vencido) — nas duas direcoes:
# constituicao (forward: puxador arrasta) e reversao (reverso: puxador liquida
# e libera). Le get_drill_pdd. NAO audita estoque/renda/caixa.


class VagaoPddForward(BaseModel):
    """Constituicao por ARRASTO: puxador vencido arrasta os a-vencer p/ faixa pior."""

    model_config = ConfigDict(extra="forbid")

    sacado_nome:         str
    faixa_para:          str = Field(description="Faixa de destino comum (pior).")
    documento_puxador:   str = Field(description="numero_documento do titulo VENCIDO que puxou.")
    qtd_arrastados:      int = Field(description="Titulos a vencer arrastados pra mesma faixa.")
    sum_delta_pdd:       float = Field(description="ΔPDD do grupo (>0, constituicao). R$.")
    bullet:              str = Field(description="1 linha factual ancorada em R$.")


class VagaoPddReverso(BaseModel):
    """Reversao por LIBERACAO: puxador vencido liquidou, liberou os a-vencer."""

    model_config = ConfigDict(extra="forbid")

    sacado_nome:         str
    documento_liberador: str = Field(description="numero_documento do VENCIDO liquidado (ex-puxador).")
    qtd_liberados:       int = Field(description="Titulos a vencer liberados (PDD revertido).")
    sum_delta_pdd:       float = Field(description="ΔPDD do grupo (<0, reversao). R$.")
    bullet:              str = Field(description="1 linha factual ancorada em R$.")


class PontoAtencaoPdd(BaseModel):
    """Ponto de atencao do PDD (anomalia de provisao)."""

    model_config = ConfigDict(extra="forbid")

    severidade: Literal["info", "atencao", "critico"]
    tipo: Literal[
        "sacado_problematico", "write_off", "divergencia_consolidado_granular", "outro"
    ]
    titulo: str
    descricao: str
    evidencia: str = Field(
        description="Cite por numero_documento (NUNCA o DID) + valores R$."
    )


class AuditoriaPddResponse(BaseModel):
    """Output do agente `controladoria.auditor_pdd` (2026-05-30).

    Lente de PROVISAO: por que a PDD ex-WOP mexeu. Separa constituicao PROPRIA
    (titulo vencido) de constituicao por ARRASTO (efeito vagao forward), e
    reversao por LIQUIDACAO (titulo proprio pagou) de reversao por LIBERACAO
    (vagao reverso: puxador liquidou e soltou os a-vencer). NAO audita estoque,
    renda nem caixa.
    """

    model_config = ConfigDict(extra="forbid")

    fundo_nome: str
    data: str = Field(description="ISO yyyy-mm-dd da data D0.")
    data_anterior: str = Field(description="ISO yyyy-mm-dd da data D-1.")

    resumo: str = Field(
        description="Leitura 5s: PDD ex-WOP variou R$ X (constituicao ou reversao), "
                    "impacto no PL Sub, e o que dominou (proprio vs arrasto/liberacao)."
    )

    pdd_ex_wop_d1: float = Field(description="Σ valor_pdd faixas A-H em D-1. R$.")
    pdd_ex_wop_d0: float = Field(description="Σ valor_pdd faixas A-H em D0. R$.")
    delta: float = Field(description="pdd_ex_wop_d0 - pdd_ex_wop_d1. R$.")
    impacto_pl_sub: float = Field(
        description="-delta. PDD que sobe REDUZ o PL Sub; PDD que cai AUMENTA. R$."
    )
    direcao: Literal["constituicao", "reversao", "neutro"]

    # ── Constituicao (PDD subiu) ───────────────────────────────────────────
    constituicao_total: float = Field(description="Σ ΔPDD>0 (PDD constituida). R$.")
    constituicao_por_arrasto: float = Field(
        description="Parte da constituicao via efeito vagao (puxador arrastou a-vencer). R$."
    )
    vagoes_forward: list[VagaoPddForward] = Field(default_factory=list)

    # ── Reversao (PDD caiu) ────────────────────────────────────────────────
    reversao_total: float = Field(description="Σ ΔPDD<0 (PDD revertida). R$.")
    reversao_por_liquidacao: float = Field(
        description="Reversao porque o PROPRIO titulo liquidou. R$ (<=0)."
    )
    reversao_por_liberacao: float = Field(
        description="Reversao por LIBERACAO do vagao (puxador saiu, soltou os a-vencer). R$ (<=0)."
    )
    vagoes_reversos: list[VagaoPddReverso] = Field(default_factory=list)

    atencao: list[PontoAtencaoPdd] = Field(
        default_factory=list,
        description="Anomalias de provisao: sacado problematico (arrasto material), "
                    "write-off, divergencia consolidado x granular. Dia limpo = [].",
    )
    conclusao: str = Field(
        description="1-3 frases: o que o controller leva sobre a provisao do dia."
    )


# ─── Auditor de Variacao de Caixa — especialista 2026-05-31 ────────────────
#
# Lente de FLUXO DE CAIXA: o que entrou (liquidacao) e saiu (cessao) bate com o
# registrado? Duas pernas + 2 tools:
#   - get_conferencia_liquidacao (entrada): floating NORMAL+CARTÓRIO -> PROV(d+1
#     util) e casa por lote; deposito sacado = imediato/agregado.
#   - get_conferencia_cessao (saida): TED exata ao cedente.
# DIRECAO point-in-time: confere PRA TRAS (caixa que caiu hoje <- origem). A
# cobranca de D0 que so pinga amanha entra como PROJECAO, nao conferencia.


class LoteFloatingCaixa(BaseModel):
    """Um lote do bucket PROV de D0, narrado: caixa de floating que pingou hoje."""

    model_config = ConfigDict(extra="forbid")

    valor:          float = Field(description="R$ do lote (1 linha LIQUIDADOS TOTAL - PROV).")
    dia_origem:     str | None = Field(
        default=None, description="ISO yyyy-mm-dd do dia cuja cobranca (NORMAL+CARTÓRIO) originou o lote."
    )
    defasagem_dias: int | None = Field(default=None, description="1=d+1, 2=d+2 (dias corridos).")
    status:         Literal["casa", "origem_nao_identificada"]
    bullet:         str = Field(description="1 linha factual ancorada em R$ e dia-origem.")


class PontoAtencaoCaixa(BaseModel):
    """Sinal de atencao no fluxo de caixa."""

    model_config = ConfigDict(extra="forbid")

    severidade: Literal["info", "atencao", "critico"]
    tipo: Literal[
        "lote_sem_origem", "floating_diverge", "honra_cedente_inadimplencia",
        "cessao_descasa", "extrato_gap", "outro",
    ]
    descricao: str
    evidencia: str = Field(description="Ancore em R$ + dia/cedente. extrato_gap NAO e erro do fundo.")


class AuditoriaVariacaoCaixaResponse(BaseModel):
    """Output do agente `controladoria.auditor_variacao_caixa` (2026-05-31).

    Lente de FLUXO DE CAIXA: confere a ENTRADA (liquidacao) e a SAIDA (cessao) de
    caixa do dia contra o registrado. Espinha PRA TRAS (point-in-time): o caixa que
    CAIU hoje rastreia a origem em dias anteriores. NAO audita estoque, renda nem
    provisao (sao dos outros 3 auditores).
    """

    model_config = ConfigDict(extra="forbid")

    fundo_nome: str
    data: str = Field(description="ISO yyyy-mm-dd da data D0.")
    data_anterior: str = Field(description="ISO yyyy-mm-dd do dia de pregao anterior.")

    resumo: str = Field(
        description="Leitura 5s: o caixa de liquidacao que pingou hoje rastreia (floating casa?), "
                    "e a cessao do dia liquidou certo (saida)?"
    )

    # ── ENTRADA por liquidacao — perna FLOATING (forte) ─────────────────────
    floating_status: Literal["casa", "diverge"] = Field(
        description="casa = todo o PROV de D0 rastreia a cobranca de dias anteriores; diverge = sobra lote."
    )
    prov_total: float = Field(description="R$ do bucket PROV de D0 (floating que pingou hoje).")
    floating_residuo: float = Field(description="prov_total - Σ lotes casados (0 = tudo rastreado).")
    lotes_floating: list[LoteFloatingCaixa] = Field(default_factory=list)

    # ── ENTRADA — perna IMEDIATA (fraca) + honra ────────────────────────────
    sacado_imediato: float = Field(description="Σ DEPOSITO SACADO de D0 (credito imediato, agregado no extrato).")
    extrato_status: Literal["conferivel_agregado", "sem_extrato"] = Field(
        description="sem_extrato = gap de sync (NAO conferivel, nao e erro do fundo)."
    )
    honra_cedente_total: float = Field(description="Σ DEPOSITO CEDENTE + RECOMPRA de D0 (cedente honrou).")
    honra_cedente_atrasada: bool = Field(description="True = 100% da honra paga em atraso (inadimplencia).")

    # ── PROJECAO forward (NAO conferencia) ──────────────────────────────────
    floating_projetado_proximo_dia: float = Field(
        description="Σ cobranca (NORMAL+CARTÓRIO) de D0 que deve pingar como PROV no proximo dia util."
    )

    # ── SAIDA por cessao ────────────────────────────────────────────────────
    cessao_total_aquisicoes: float = Field(description="Σ valor_compra das aquisicoes de D0 (saida esperada).")
    cessao_status: Literal["casa", "descasa", "sem_extrato", "sem_cessao"] = Field(
        description="casa = TED ao cedente bate a compra; descasa = diverge (erro de lancamento); "
                    "sem_extrato = gap; sem_cessao = nao houve aquisicao material."
    )
    cessao_n_descasa: int = Field(default=0, description="Qtd de cedentes que descasaram.")

    atencao: list[PontoAtencaoCaixa] = Field(
        default_factory=list,
        description="Sinais: lote sem origem, floating diverge, honra cedente em atraso, cessao descasa. "
                    "extrato_gap e info (nao erro). Dia limpo = [].",
    )
    conclusao: str = Field(
        description="1-3 frases: o que o controller leva sobre o caixa do dia (entrada + saida)."
    )


# ─── Auditor de Notas Comerciais (Op. Estruturadas) — especialista 2026-05-31 ──
#
# Lente da linha "Op. Estruturadas" do balanco (= Notas Comerciais, papeis NCPX/
# VCNC/PDDNC em wh_posicao_renda_fixa). POSICAO-FIRST: a posicao e a fonte
# autoritativa do movimento; o extrato so confirma valor (a liquidacao da NC vem
# como transferencia interna do fundo, generica a DC+NC, sem mostrar o devedor).
# NAO audita DC, caixa, renda nem provisao.


class PontoAtencaoNC(BaseModel):
    """Sinal de atencao numa NC."""

    model_config = ConfigDict(extra="forbid")

    severidade: Literal["info", "atencao", "critico"]
    tipo: Literal[
        "amortizacao_sem_extrato", "emitente_tambem_cedente",
        "aquisicao_sem_debito", "vencido_nao_quitado", "outro",
    ]
    descricao: str
    evidencia: str = Field(description="Ancore em R$ + codigo/emitente.")


class MovimentoNCItem(BaseModel):
    """Um movimento de NC narrado (aquisicao/amortizacao/quitacao/apropriacao)."""

    model_config = ConfigDict(extra="forbid")

    codigo:       str
    emitente:     str
    tipo:         Literal["aquisicao", "amortizacao", "quitacao", "apropriacao"]
    valor:        float = Field(
        description="R$ do evento: valor aplicado (aquisicao) | reducao liquida (amort/quit) | carrego (apropriacao)."
    )
    extrato_confirma: bool = Field(
        description="Sinal SOFT: existe lancamento de valor compativel no extrato? Indicio, nao prova."
    )
    bullet:       str = Field(description="1 linha factual: codigo, emitente, R$.")


class AuditoriaNotaComercialResponse(BaseModel):
    """Output do agente `controladoria.auditor_notas_comerciais` (2026-05-31).

    Lente de Op. Estruturadas (Notas Comerciais). Abre o ΔSaldo da linha em
    aquisicao / amortizacao / quitacao / apropriacao por codigo. POSICAO-FIRST:
    a posicao manda; o extrato e sinal soft (liquidacao da NC = transferencia
    interna do fundo, nao mostra o devedor). NAO audita DC, caixa nem provisao.
    """

    model_config = ConfigDict(extra="forbid")

    fundo_nome: str
    data: str = Field(description="ISO yyyy-mm-dd da data D0.")
    data_anterior: str = Field(description="ISO yyyy-mm-dd do dia anterior.")

    resumo: str = Field(
        description="Leitura 5s: a posicao de NC variou R$ X — quanto foi aquisicao nova, "
                    "amortizacao/quitacao (caixa entrou) e carrego (juros)."
    )

    posicao_d1: float = Field(description="Σ valor_bruto das NCs em D-1. R$.")
    posicao_d0: float = Field(description="Σ valor_bruto das NCs em D0. R$.")
    delta_posicao: float = Field(description="posicao_d0 - posicao_d1 (= ΔSaldo da linha Op. Estruturadas). R$.")

    total_aquisicao: float = Field(description="Σ valor aplicado em NCs novas (caixa que saiu). R$.")
    total_amortizacao: float = Field(description="Σ reducao liquida (amortizacao + quitacao; caixa que entrou). R$.")
    total_apropriacao: float = Field(description="Σ carrego do dia (juros das NCs que ficaram). R$.")

    movimentos: list[MovimentoNCItem] = Field(
        default_factory=list,
        description="Movimentos materiais por NC. Carrego imaterial pode ser omitido.",
    )
    atencao: list[PontoAtencaoNC] = Field(
        default_factory=list,
        description="Sinais: amortizacao/quitacao sem confirmacao no extrato, emitente que "
                    "tambem e cedente de DC (ambiguidade), NC vencida nao quitada. Dia rotineiro = [].",
    )
    conclusao: str = Field(
        description="1-3 frases: o que mexeu na carteira de NC e se ha algo a acompanhar."
    )
