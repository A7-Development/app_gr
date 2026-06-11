"""Check: contrato_social_consistente — contrato social x cadastro oficial.

A família de cruzamento "consistência cross-fonte" aplicada ao documento
societário: o contrato social homologado deve bater com o registro oficial
(BDC) já materializado no dossiê — CNPJ (é a empresa-alvo?), razão social,
capital social e data de constituição. Divergência vira red flag estruturada
com proveniência (expected = oficial, actual = contrato).

Função pura sobre o payload determinístico de
`services/social_contract.build_societario_payload` (mesma fonte da
read-tool do agente e da tela — um fato, três consumidores). O node
`deterministic_check` persiste flags + decision_log.
"""

from __future__ import annotations

from app.agentic.tools.credito.checks._base import (
    CheckContext,
    CheckResult,
    FlagSpec,
    register_check,
)

# CNPJ divergente = documento de OUTRA empresa — crítico. Demais = importante.
_SEVERITY_BY_FIELD = {
    "cnpj": "critical",
    "razao_social": "important",
    "capital_social": "important",
    "data_constituicao": "important",
}

_FIELD_LABEL = {
    "cnpj": "CNPJ",
    "razao_social": "Razão social",
    "capital_social": "Capital social",
    "data_constituicao": "Data de constituição",
}


@register_check(
    name="contrato_social_consistente",
    label="Contrato social x cadastro oficial",
    description=(
        "Cruza o contrato social homologado com o registro oficial (BDC): "
        "CNPJ é o da empresa-alvo? Razão social, capital social e data de "
        "constituição conferem? Divergência vira red flag com proveniência."
    ),
)
async def contrato_social_consistente(ctx: CheckContext) -> CheckResult:
    from app.modules.credito.services.social_contract import (
        build_societario_payload,
    )

    payload = await build_societario_payload(
        ctx.db, tenant_id=ctx.tenant_id, dossier_id=ctx.dossier_id
    )

    if not payload.get("encontrado"):
        return CheckResult(
            passed=False,
            flags=[
                FlagSpec(
                    severity="important",
                    title="Contrato social ausente",
                    description=(
                        "Nenhum contrato social extraído no dossiê — não há "
                        "base para validar a estrutura societária."
                    ),
                    evidence="documento social_contract não encontrado",
                    check_type="contrato_social_consistente",
                    provenance={
                        "check_type": "contrato_social_consistente",
                        "source": "credit_dossier_document",
                        "field": "social_contract",
                        "detail": "documento ausente ou sem extração",
                    },
                    section="social_contract",
                )
            ],
            decision_inputs={"encontrado": False},
            decision_output={"passed": False},
            summary="Contrato social ausente — sem base para o cruzamento.",
        )

    cruzamentos = payload.get("cruzamentos") or []
    estrutura = payload.get("estrutura") or {}
    fonte = payload.get("fonte") or {}

    flags: list[FlagSpec] = []
    for cz in cruzamentos:
        if cz.get("confere") is not False:
            continue
        campo = str(cz.get("campo"))
        label = _FIELD_LABEL.get(campo, campo)
        flags.append(
            FlagSpec(
                severity=_SEVERITY_BY_FIELD.get(campo, "important"),
                title=f"{label}: contrato diverge do registro oficial",
                description=str(cz.get("detalhe") or f"{label} divergente."),
                evidence=(
                    f"contrato={cz.get('contrato')} · oficial={cz.get('oficial')} "
                    f"(doc: {fonte.get('arquivo')})"
                ),
                check_type="contrato_social_consistente",
                provenance={
                    "check_type": "contrato_social_consistente",
                    "source": "social_contract x cadastral_oficial",
                    "field": campo,
                    "expected_value": cz.get("oficial"),
                    "actual_value": cz.get("contrato"),
                    "detail": cz.get("detalhe"),
                },
                section="social_contract",
            )
        )

    # Soma das participações fora de 100% também é inconsistência estrutural
    # (o ownership_sum cobre o grafo persistido; aqui cobrimos o DOCUMENTO).
    if estrutura.get("soma_confere") is False:
        flags.append(
            FlagSpec(
                severity="important",
                title="Participações dos sócios não somam 100%",
                description=(
                    f"As participações declaradas no contrato somam "
                    f"{estrutura.get('soma_participacoes_pct')}% — sócio "
                    "faltante/oculto ou erro de extração."
                ),
                evidence=f"soma={estrutura.get('soma_participacoes_pct')}%",
                check_type="contrato_social_consistente",
                provenance={
                    "check_type": "contrato_social_consistente",
                    "source": "social_contract",
                    "field": "soma_participacoes_pct",
                    "expected_value": 100,
                    "actual_value": estrutura.get("soma_participacoes_pct"),
                    "detail": "QSA do contrato não fecha em 100%",
                },
                section="social_contract",
            )
        )

    has_critical = any(f.severity == "critical" for f in flags)
    return CheckResult(
        passed=not has_critical,
        flags=flags,
        decision_inputs={
            "documento": fonte.get("arquivo"),
            "homologado": payload.get("homologado"),
            "cruzamentos": cruzamentos,
            "estrutura": estrutura,
        },
        decision_output={
            "passed": not has_critical,
            "divergencias": len(flags),
        },
        summary=(
            "Contrato social confere com o registro oficial."
            if not flags
            else f"{len(flags)} divergência(s) entre contrato e registro oficial."
        ),
    )
