"""Check: company_status_active — eligibility gate by tax registration status.

Reads the active `credit_policy` (`params.status_permitidos`, default
["ATIVA"]) and the TARGET company's `tax_status` (cadastral BDC), and decides
whether the cedente's registration status is allowed. ELEGIBILITY gate (handoff
§8) — a policy rejection, not a fraud flag — so it raises no red_flag; returns
`passed` for the `conditional_branch` and the node records a RULE_EVALUATION.
"""

from __future__ import annotations

from sqlalchemy import select

from app.agentic.tools.credito.checks._base import (
    CheckContext,
    CheckResult,
    register_check,
)
from app.core.enums import CompanyRole

_DEFAULT_ALLOWED = ["ATIVA"]


@register_check(
    name="company_status_active",
    label="Situacao cadastral (ativa)",
    description=(
        "Gate de elegibilidade: reprova cedentes cuja situacao cadastral nao "
        "esta em credit_policy.params.status_permitidos (default ['ATIVA']). "
        "Le credit_dossier_company.tax_status (cadastral BDC)."
    ),
)
async def company_status_active(ctx: CheckContext) -> CheckResult:
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

    params = (policy.params or {}) if policy is not None else {}
    allowed = params.get("status_permitidos") or _DEFAULT_ALLOWED
    allowed_norm = {str(s).strip().upper() for s in allowed}

    target = (
        await ctx.db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == ctx.tenant_id,
                CreditDossierCompany.dossier_id == ctx.dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()
    status = target.tax_status if target is not None else None

    inputs = {
        "policy": policy.full_id if policy is not None else None,
        "policy_name": policy_name,
        "status_permitidos": sorted(allowed_norm),
        "tax_status": status,
        "cnpj": target.cnpj if target is not None else None,
    }

    if status is None:
        return CheckResult(
            passed=False,
            decision_inputs=inputs,
            decision_output={"passed": False, "reason": "tax_status ausente"},
            summary=(
                "Situacao cadastral ausente — rode a consulta cadastral antes "
                "do gate."
            ),
        )

    passed = str(status).strip().upper() in allowed_norm
    return CheckResult(
        passed=passed,
        decision_inputs=inputs,
        decision_output={"passed": passed, "tax_status": status},
        summary=(
            f"Situacao cadastral '{status}'. "
            + (
                "Elegivel."
                if passed
                else f"Reprovada (permitidas: {', '.join(sorted(allowed_norm))})."
            )
        ),
    )
