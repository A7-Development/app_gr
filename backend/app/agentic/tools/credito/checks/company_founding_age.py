"""Check: company_founding_age — eligibility gate by company age.

Reads the active `credit_policy` (`min_company_age_years`) and the TARGET
company's `founding_date`, and decides whether the cedente meets the minimum
age. This is an ELEGIBILITY gate (handoff §8) — a policy rejection, not a
fraud flag — so it raises no red_flag; it returns `passed` for the
`conditional_branch` to route on, and the node records a RULE_EVALUATION in
decision_log (with which policy version vetoed).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.agentic.tools.credito.checks._base import (
    CheckContext,
    CheckResult,
    register_check,
)
from app.core.enums import CompanyRole


@register_check(
    name="company_founding_age",
    label="Idade da empresa (tempo de fundacao)",
    description=(
        "Gate de elegibilidade: reprova cedentes com menos de N anos de "
        "fundacao. N vem de credit_policy.min_company_age_years (versao ativa)."
    ),
)
async def company_founding_age(ctx: CheckContext) -> CheckResult:
    from app.modules.credito.models.company import CreditDossierCompany
    from app.modules.credito.models.policy import CreditPolicy, CreditPolicyActive

    policy_name = ctx.config.get("policy_name") or "default"

    active = (
        await ctx.db.execute(
            select(CreditPolicyActive).where(
                CreditPolicyActive.tenant_id == ctx.tenant_id,
                CreditPolicyActive.name == policy_name,
            )
        )
    ).scalar_one_or_none()

    policy = None
    if active is not None:
        policy = (
            await ctx.db.execute(
                select(CreditPolicy).where(
                    CreditPolicy.tenant_id == ctx.tenant_id,
                    CreditPolicy.name == policy_name,
                    CreditPolicy.version == active.active_version,
                )
            )
        ).scalar_one_or_none()

    min_age = policy.min_company_age_years if policy is not None else None

    target = (
        await ctx.db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == ctx.tenant_id,
                CreditDossierCompany.dossier_id == ctx.dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()
    founding = target.founding_date if target is not None else None

    inputs = {
        "policy": policy.full_id if policy is not None else None,
        "policy_name": policy_name,
        "min_company_age_years": min_age,
        "founding_date": founding.isoformat() if founding else None,
        "cnpj": target.cnpj if target is not None else None,
    }

    if min_age is None:
        return CheckResult(
            passed=True,
            decision_inputs=inputs,
            decision_output={"passed": True, "reason": "politica sem corte de idade"},
            summary="Politica ativa nao define idade minima — sem corte por idade.",
        )

    if founding is None:
        return CheckResult(
            passed=False,
            decision_inputs=inputs,
            decision_output={"passed": False, "reason": "founding_date ausente"},
            summary=(
                "Data de fundacao ausente — nao foi possivel confirmar a idade "
                f"minima de {min_age} anos."
            ),
        )

    age_years = (date.today() - founding).days / 365.25
    passed = age_years >= min_age
    return CheckResult(
        passed=passed,
        decision_inputs=inputs,
        decision_output={
            "passed": passed,
            "age_years": round(age_years, 2),
            "min_company_age_years": min_age,
        },
        summary=(
            f"Empresa com {age_years:.1f} anos de fundacao (minimo {min_age}). "
            + ("Elegivel." if passed else "Reprovada por idade.")
        ),
    )
