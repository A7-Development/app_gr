"""Descriptor builders — agent output -> SectionDescriptor (A1 home).

These are the BACKEND home for the section mappers (decision A1: the backend
builds the descriptor). They mirror the interim frontend mappers in
``app/(foco)/credito/dossies/[id]/_lib/section-mappers.ts``; when an endpoint
serves ``DossierDescriptor`` (Phase 1 / Etapa 4), the cockpit consumes these and
the frontend mappers are deleted.

Pure functions: agent output (typed Pydantic) -> SectionDescriptor. No DB, no
I/O — unit-testable in isolation. The judgment layer only; the deterministic
"consulta/silver" producer (revenue numbers, cadastral fields, societario facts)
becomes Ficha/Tabela blocks via the Data Contract in Etapa 4.

See docs/esteira-credito-interface-camadas.md.
"""

from __future__ import annotations

from typing import Literal

from app.agentic.engine.output_schemas import (
    CadastralAnalysis,
    RevenueAnalysis,
    SocialContractAnalysis,
)
from app.agentic.workflows.schemas.section_descriptor import (
    Apontamento,
    ApontamentosBlock,
    Block,
    ConclusaoAgenteBlock,
    FichaBadge,
    FichaBlock,
    FichaCampo,
    SectionDescriptor,
    TextoBlock,
)

Severidade = Literal["critico", "atencao", "info"]


def _sev_from_pt(s: str) -> Severidade:
    """'alta/media/baixa' (revenue, cadastral) -> severidade canônica."""
    return "critico" if s == "alta" else "atencao" if s == "media" else "info"


def _sev_from_checklist(s: str) -> Severidade:
    """status do checklist (social) -> severidade canônica."""
    return "critico" if s == "critical" else "atencao" if s == "alert" else "info"


# ─── Faturamento (revenue_analyst) ────────────────────────────────────────────


def revenue_to_section(output: RevenueAnalysis) -> SectionDescriptor:
    cred_nivel = output.credibilidade_documento.nivel
    blocks: list[Block] = [
        ConclusaoAgenteBlock(
            id="rev-conclusao", agente="Faturamento", resumo=output.resumo_executivo
        ),
        FichaBlock(
            id="rev-leituras",
            campos=[
                FichaCampo(
                    label="Tendência",
                    valor=f"{output.tendencia.direcao} · {output.tendencia.intensidade}",
                    nota=output.tendencia.leitura,
                ),
                FichaCampo(
                    label="Sazonalidade",
                    valor="Detectada" if output.sazonalidade.detectada else "Sem padrão claro",
                    nota=output.sazonalidade.padrao,
                    badge=None
                    if output.sazonalidade.confiavel
                    else FichaBadge(texto="leitura fraca", tom="neutro"),
                ),
                FichaCampo(
                    label="Qualidade do dado",
                    valor=(
                        f"{output.qualidade_do_dado.n_meses} mês(es)"
                        + (
                            f" · faltam {len(output.qualidade_do_dado.meses_faltantes)}"
                            if output.qualidade_do_dado.meses_faltantes
                            else ""
                        )
                    ),
                    nota=output.qualidade_do_dado.observacao,
                    badge=(
                        FichaBadge(texto="soma confere", tom="ok")
                        if output.qualidade_do_dado.soma_confere
                        else FichaBadge(texto="soma ≠", tom="atencao")
                    ),
                ),
                FichaCampo(
                    label="Credibilidade do documento",
                    valor=cred_nivel,
                    nota=output.credibilidade_documento.leitura,
                    badge=(
                        FichaBadge(texto="alto", tom="ok")
                        if cred_nivel == "alto"
                        else FichaBadge(texto="baixo", tom="critico")
                        if cred_nivel == "baixo"
                        else FichaBadge(texto="médio", tom="atencao")
                    ),
                ),
            ],
        ),
    ]

    if output.pontos_de_atencao:
        blocks.append(
            ApontamentosBlock(
                id="rev-pontos",
                itens=[
                    Apontamento(
                        severidade=_sev_from_pt(p.severidade),
                        titulo=(
                            f"{f'{p.mes} · ' if p.mes else ''}{p.tipo} ({p.esperado_ou_anomalo})"
                        ),
                        descricao=p.observacao,
                    )
                    for p in output.pontos_de_atencao
                ],
            )
        )

    if output.credibilidade_documento.ressalvas:
        blocks.append(
            ApontamentosBlock(
                id="rev-ressalvas",
                titulo="Ressalvas do documento",
                itens=[
                    Apontamento(severidade="atencao", titulo=r)
                    for r in output.credibilidade_documento.ressalvas
                ],
            )
        )

    blocks.append(
        TextoBlock(
            id="rev-leitura-credito",
            titulo="Leitura para crédito",
            markdown=output.leitura_para_credito,
        )
    )

    return SectionDescriptor(
        id="section-revenue",
        station_id="faturamento",
        titulo="Faturamento",
        blocks=blocks,
        generates_dossier_section=True,
    )


# ─── Cadastral (cadastral_analyst) ─────────────────────────────────────────────


def cadastral_to_section(output: CadastralAnalysis) -> SectionDescriptor:
    sit = output.situacao_cadastral
    sit_tom: Literal["ok", "critico", "neutro"] = (
        "ok" if sit == "ativa" else "critico" if sit == "irregular" else "neutro"
    )
    blocks: list[Block] = [
        ConclusaoAgenteBlock(
            id="cad-conclusao", agente="Cadastral", resumo=output.resumo_executivo
        ),
        FichaBlock(
            id="cad-leituras",
            campos=[
                FichaCampo(
                    label="Situação cadastral",
                    valor=sit,
                    badge=FichaBadge(texto=sit, tom=sit_tom),
                ),
                FichaCampo(label="Tempo de atividade", valor=output.tempo_atividade_leitura),
                FichaCampo(
                    label="Aderência da atividade (CNAE)", valor=output.aderencia_atividade
                ),
                FichaCampo(label="Capital vs porte", valor=output.porte_capital_leitura),
            ],
        ),
    ]

    if output.pontos_de_atencao:
        blocks.append(
            ApontamentosBlock(
                id="cad-pontos",
                itens=[
                    Apontamento(
                        severidade=_sev_from_pt(p.severidade),
                        titulo=p.tipo,
                        descricao=p.observacao,
                    )
                    for p in output.pontos_de_atencao
                ],
            )
        )

    blocks.append(
        TextoBlock(
            id="cad-leitura-credito",
            titulo="Leitura para crédito",
            markdown=output.leitura_para_credito,
        )
    )

    return SectionDescriptor(
        id="section-cadastral",
        station_id="cadastral",
        titulo="Cadastral",
        blocks=blocks,
        generates_dossier_section=True,
    )


# ─── Contrato social (social_contract_analyst) ─────────────────────────────────


def social_contract_to_section(output: SocialContractAnalysis) -> SectionDescriptor:
    blocks: list[Block] = [
        ConclusaoAgenteBlock(
            id="soc-conclusao", agente="Contrato social", resumo=output.summary
        ),
        FichaBlock(
            id="soc-leituras",
            campos=[
                FichaCampo(
                    label="Alterações recentes de QSA (24m)",
                    valor="Sim — atenção" if output.qsa_changes_recent else "Não identificadas",
                    nota=output.qsa_changes_detail,
                    badge=FichaBadge(texto="atenção", tom="atencao")
                    if output.qsa_changes_recent
                    else None,
                ),
                FichaCampo(
                    label="Objeto social x operação",
                    valor="Compatível"
                    if output.object_compatible_with_operation
                    else "Incompatível",
                    nota=output.object_compatibility_rationale,
                    badge=(
                        FichaBadge(texto="compatível", tom="ok")
                        if output.object_compatible_with_operation
                        else FichaBadge(texto="incompatível", tom="critico")
                    ),
                ),
            ],
        ),
    ]

    signing = output.signing_powers or {}
    if signing:
        blocks.append(
            FichaBlock(
                id="soc-poderes",
                titulo="Poderes de assinatura",
                campos=[
                    FichaCampo(label=nome, valor=str(forma)) for nome, forma in signing.items()
                ],
            )
        )

    if output.statutory_restrictions:
        blocks.append(
            TextoBlock(
                id="soc-restricoes",
                titulo="Restrições estatutárias",
                markdown="\n".join(f"- {r}" for r in output.statutory_restrictions),
            )
        )

    if output.checklist_results:
        blocks.append(
            ApontamentosBlock(
                id="soc-checklist",
                titulo="Checklist",
                itens=[
                    Apontamento(
                        severidade=_sev_from_checklist(c.status),
                        titulo=f"{c.code} — {c.description}",
                        descricao=c.rationale,
                    )
                    for c in output.checklist_results
                ],
            )
        )

    return SectionDescriptor(
        id="section-social",
        station_id="contrato-social",
        titulo="Contrato social",
        blocks=blocks,
        generates_dossier_section=True,
    )
