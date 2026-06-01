"""DeterministicCheckNode — runs a pure-Python credit check (no LLM).

The reusable builder block for the "calculo e regra sao tools, nao agentes"
principle (handoff §6/§7) and the cheap eligibility gate that runs BEFORE
paid bureau queries (sequenciamento por custo, §8/§9).

It resolves a registered check by name (`config.check`), runs it over the
persisted dossier graph, then applies the side effects the check itself never
does:
  1. records ONE `decision_log` entry (RULE_EVALUATION) for the evaluation,
  2. materializes each structured `red_flag` the check produced, linked to
     that decision_log entry (the auditable cross-check, §1/§14).

Output exposes `result` (bool) so an outgoing `conditional_branch`/edge can
route on `{{node.<id>.output.result}} == true` (e.g. gate: reprova -> fim).

Config schema:
    {
        "check": "company_founding_age",   # required — registered check name
        "policy_name": "default",          # optional — credit_policy to read
        "tolerance_pct": 0.5               # optional — for sum-style checks
    }
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.playbooks.nodes._base import (
    BaseNode,
    NodeContext,
    NodeOutput,
    VarType,
)

# Importing the checks package registers every check (side-effect), so
# CHECK_REGISTRY is populated by the time a node validates/executes.
from app.agentic.tools.credito import checks as credito_checks
from app.shared.audit_log.decision_log import DecisionLog, DecisionType


class DeterministicCheckNode(BaseNode):
    """Runs a registered deterministic check; emits decision_log + red_flags."""

    type = "deterministic_check"

    def validate_config(self) -> None:
        check_name = self.config.get("check")
        if not check_name:
            raise ValueError(
                "deterministic_check: `config.check` e obrigatorio (nome do check)."
            )
        if check_name not in credito_checks.CHECK_REGISTRY:
            raise ValueError(
                f"deterministic_check: check '{check_name}' nao registrado. "
                f"Conhecidos: {sorted(credito_checks.CHECK_REGISTRY)}"
            )

    def produces(self) -> dict[str, VarType]:
        return {"result": VarType.BOOLEAN, "flags_raised": VarType.NUMBER}

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        from app.modules.credito.models.red_flag import CreditDossierRedFlag

        check_name = self.config["check"]
        meta = credito_checks.get_check(check_name)

        dossier_id_raw = ctx.trigger_data.get("dossier_id")
        if not dossier_id_raw:
            raise ValueError(
                "deterministic_check: trigger_data.dossier_id ausente — "
                "node de credito exige um dossie."
            )
        dossier_id = UUID(str(dossier_id_raw))

        check_ctx = credito_checks.CheckContext(
            db=db,
            tenant_id=ctx.tenant_id,
            dossier_id=dossier_id,
            config=self.config,
        )
        result = await meta.fn(check_ctx)

        # 1 entrada de decision_log (RULE_EVALUATION) por avaliacao.
        log = DecisionLog(
            tenant_id=ctx.tenant_id,
            decision_type=DecisionType.RULE_EVALUATION,
            rule_or_model=f"check:{check_name}",
            rule_or_model_version=result.decision_inputs.get("policy"),
            inputs_ref=result.decision_inputs,
            output=result.decision_output,
            explanation=result.summary or None,
            triggered_by=f"deterministic_check:{ctx.node_id}",
        )
        db.add(log)
        await db.flush()

        # Materializa as flags estruturadas linkadas ao decision_log.
        flag_ids: list[str] = []
        for f in result.flags:
            flag = CreditDossierRedFlag(
                tenant_id=ctx.tenant_id,
                dossier_id=dossier_id,
                section=f.section,
                severity=f.severity,
                title=f.title[:200],
                description=f.description,
                evidence=f.evidence,
                check_type=f.check_type,
                provenance=f.provenance,
                decision_log_id=log.id,
            )
            db.add(flag)
            await db.flush()
            flag_ids.append(str(flag.id))

        return NodeOutput(
            data={
                "result": result.passed,
                "passed": result.passed,
                "check": check_name,
                "flags_raised": len(result.flags),
                "flag_ids": flag_ids,
                "summary": result.summary,
                "output": result.decision_output,
                "decision_log_id": str(log.id),
            },
            status_hint=(result.summary[:120] if result.summary else None),
        )
