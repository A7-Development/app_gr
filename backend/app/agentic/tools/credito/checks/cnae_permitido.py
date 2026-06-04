"""Check: cnae_permitido — eligibility gate by economic activity (CNAE).

Reads the active `credit_policy` (`forbidden_cnae`) and the TARGET company's
`cnaes` (main + secondary, cadastral BDC), normalizes both (digits only) and
reproves if any company CNAE is forbidden. ELEGIBILITY gate (handoff §8) — a
policy rejection, not a fraud flag — so it raises no red_flag; returns `passed`
for the `conditional_branch` and the node records a RULE_EVALUATION.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from app.agentic.tools.credito.checks._base import (
    CheckContext,
    CheckResult,
    register_check,
)
from app.core.enums import CompanyRole


def _norm(code: object) -> str:
    """Normaliza CNAE pra comparacao por digitos (ignora mascara/pontuacao)."""
    return re.sub(r"\D", "", str(code or ""))


@register_check(
    name="cnae_permitido",
    label="CNAE permitido (atividade nao vetada)",
    description=(
        "Gate de elegibilidade: reprova se algum CNAE (principal ou secundario) "
        "da empresa esta em credit_policy.forbidden_cnae. Le "
        "credit_dossier_company.cnaes (cadastral BDC). Compara por digitos "
        "(ignora mascara)."
    ),
)
async def cnae_permitido(ctx: CheckContext) -> CheckResult:
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

    forbidden_raw = (policy.forbidden_cnae or []) if policy is not None else []
    forbidden = {_norm(c) for c in forbidden_raw if _norm(c)}

    target = (
        await ctx.db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == ctx.tenant_id,
                CreditDossierCompany.dossier_id == ctx.dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()

    # cnaes: list de {code, is_main, name?} OU list de strings.
    cnaes_raw = (target.cnaes or []) if target is not None else []
    company_pairs: list[tuple[str, object]] = []
    for item in cnaes_raw:
        code = item.get("code") if isinstance(item, dict) else item
        if _norm(code):
            company_pairs.append((_norm(code), code))

    inputs = {
        "policy": policy.full_id if policy is not None else None,
        "policy_name": policy_name,
        "forbidden_cnae": sorted(forbidden),
        "company_cnaes": [orig for _, orig in company_pairs],
        "cnpj": target.cnpj if target is not None else None,
    }

    if not forbidden:
        return CheckResult(
            passed=True,
            decision_inputs=inputs,
            decision_output={"passed": True, "reason": "politica sem CNAEs vetados"},
            summary="Politica ativa nao veta CNAEs — sem corte por atividade.",
        )

    if not company_pairs:
        return CheckResult(
            passed=False,
            decision_inputs=inputs,
            decision_output={"passed": False, "reason": "cnaes ausentes"},
            summary="CNAEs da empresa ausentes — rode a consulta cadastral antes do gate.",
        )

    hits = [orig for norm, orig in company_pairs if norm in forbidden]
    passed = not hits
    return CheckResult(
        passed=passed,
        decision_inputs=inputs,
        decision_output={"passed": passed, "cnae_vetados_encontrados": hits},
        summary=(
            "Nenhum CNAE vetado — elegivel por atividade."
            if passed
            else f"CNAE vetado encontrado: {', '.join(str(h) for h in hits)}. Reprovada."
        ),
    )
