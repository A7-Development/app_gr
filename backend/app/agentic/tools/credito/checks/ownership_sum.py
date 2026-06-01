"""Check: ownership_sum — partners' ownership must sum to ~100%.

A cross-check (handoff §6, family "consistencia cross-fonte"): the declared
ownership percentages of the partners should add up to ~100%. A divergence
(or a partner with no percentage) is a structured red flag — it can mean a
missing/hidden partner (laranja, socio oculto) or a cadastral error. Pure
function over the persisted graph; the node persists the flag + decision_log.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.agentic.tools.credito.checks._base import (
    CheckContext,
    CheckResult,
    FlagSpec,
    register_check,
)
from app.core.enums import CompanyRole, PersonRole

_HUNDRED = Decimal("100")


@register_check(
    name="ownership_sum",
    label="Soma das participacoes dos socios",
    description=(
        "Sinaliza quando a soma das participacoes dos socios diverge de 100% "
        "(socio faltante/oculto ou erro cadastral). Tolerancia via config."
    ),
)
async def ownership_sum(ctx: CheckContext) -> CheckResult:
    from app.modules.credito.models.company import CreditDossierCompany
    from app.modules.credito.models.person import CreditDossierPerson

    target = (
        await ctx.db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == ctx.tenant_id,
                CreditDossierCompany.dossier_id == ctx.dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()
    company_cnpj = target.cnpj if target is not None else None

    query = select(CreditDossierPerson).where(
        CreditDossierPerson.tenant_id == ctx.tenant_id,
        CreditDossierPerson.dossier_id == ctx.dossier_id,
        CreditDossierPerson.role == PersonRole.PARTNER,
    )
    if company_cnpj is not None:
        query = query.where(CreditDossierPerson.company_cnpj == company_cnpj)
    socios = list((await ctx.db.execute(query)).scalars().all())

    try:
        tolerance = Decimal(str(ctx.config.get("tolerance_pct", "0.5")))
    except Exception:
        tolerance = Decimal("0.5")

    if not socios:
        return CheckResult(
            passed=True,
            decision_inputs={"company_cnpj": company_cnpj, "n_socios": 0},
            decision_output={"passed": True, "reason": "sem socios informados"},
            summary="Nenhum socio informado — nada a cruzar.",
        )

    total = Decimal("0")
    missing = 0
    comparisons: list[dict] = []
    for s in socios:
        pct = s.ownership_pct
        if pct is None:
            missing += 1
        else:
            total += pct
        comparisons.append(
            {
                "source": "self_declared:cadastro",
                "field": s.name,
                "value": (float(pct) if pct is not None else None),
            }
        )

    delta = total - _HUNDRED
    within = abs(delta) <= tolerance and missing == 0

    inputs = {
        "company_cnpj": company_cnpj,
        "n_socios": len(socios),
        "soma_pct": float(total),
        "missing_pct_count": missing,
    }
    output = {
        "passed": within,
        "soma_pct": float(total),
        "delta": float(delta),
        "missing_pct_count": missing,
    }

    flags: list[FlagSpec] = []
    if not within:
        if missing > 0:
            desc = (
                f"{missing} socio(s) sem percentual informado; soma dos "
                f"informados = {total}%."
            )
        else:
            desc = (
                f"Soma das participacoes = {total}% (esperado ~100%, "
                f"divergencia de {delta:+}%)."
            )
        evidence = "Socios: " + "; ".join(
            f"{c['field']}={c['value']}%" for c in comparisons
        )
        flags.append(
            FlagSpec(
                severity="important",
                title="Soma de participacoes diverge de 100%",
                description=(
                    desc + " Pode indicar socio faltante/oculto ou erro cadastral."
                ),
                evidence=evidence,
                check_type="ownership_sum",
                provenance={
                    "check_type": "ownership_sum",
                    "source": "self_declared:cadastro",
                    "field": "ownership_pct",
                    "expected_value": 100,
                    "actual_value": float(total),
                    "comparisons": comparisons,
                    "detail": {"missing_pct_count": missing, "delta": float(delta)},
                },
                section="partners",
            )
        )

    summary = (
        "Participacoes somam ~100%."
        if within
        else f"Divergencia na soma de participacoes: {total}%."
    )
    return CheckResult(
        passed=within,
        flags=flags,
        decision_inputs=inputs,
        decision_output=output,
        summary=summary,
    )
