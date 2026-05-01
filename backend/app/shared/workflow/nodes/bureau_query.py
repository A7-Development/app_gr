"""BureauQueryNode — consulta bureau externo (Serasa, BigDataCorp, etc).

Config schema:
    {
        "adapter": "serasa_pj" | "serasa_pf" | "bigdatacorp" | "infosimples",
        "entity_type": "company" | "person",
        "entity_ref": "<doc>" | "{{trigger.cnpj}}" | "{{node.X.output.target_cnpj}}",
        "environment": "production" | "sandbox",   # opcional, default production
    }

Quando o engine instancia o no, `entity_ref` ja vem RESOLVIDO (template
substituido por CNPJ literal). O adapter cuida da normalizacao (mascara
e digitos).

Adapters wired:
    - serasa_pj: consulta Business Information Report (PJ analitico),
      grava raw + silver, e devolve consulta_id pra nodes downstream
      referenciarem (ex.: agentes especialistas que leem do warehouse).

Adapters ainda placeholder:
    - serasa_pf, bigdatacorp, infosimples — retornam status "em breve".

Falha de consulta (auth, rede, contrato) levanta excecao — engine marca
o `workflow_node_run` como FAILED. Operador pode reprocessar ou pular.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Environment
from app.modules.integracoes.public import execute_serasa_pj_query
from app.shared.workflow.nodes._base import BaseNode, NodeContext, NodeOutput

_SUPPORTED_ADAPTERS = {"serasa_pj", "serasa_pf", "bigdatacorp", "infosimples"}
_WIRED_ADAPTERS = {"serasa_pj"}  # outros caem no placeholder


class BureauQueryNode(BaseNode):
    """Bureau query — Serasa PJ wired; demais adapters placeholder."""

    type = "bureau_query"

    def validate_config(self) -> None:
        adapter = self.config.get("adapter")
        if adapter not in _SUPPORTED_ADAPTERS:
            raise ValueError(
                f"bureau_query: adapter '{adapter}' nao suportado. "
                f"Aceitos: {sorted(_SUPPORTED_ADAPTERS)}."
            )

        if adapter in _WIRED_ADAPTERS:
            entity_ref = self.config.get("entity_ref")
            if not isinstance(entity_ref, str) or not entity_ref.strip():
                raise ValueError(
                    f"bureau_query[{adapter}]: 'entity_ref' obrigatorio "
                    "(string com documento ou template `{{trigger.cnpj}}`)."
                )
            env = self.config.get("environment", "production")
            if env not in {"production", "sandbox"}:
                raise ValueError(
                    f"bureau_query[{adapter}]: 'environment' invalido "
                    f"(='{env}'). Use 'production' ou 'sandbox'."
                )

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        adapter = self.config["adapter"]

        if adapter == "serasa_pj":
            return await self._execute_serasa_pj(ctx)

        # Adapters ainda nao wired.
        return NodeOutput(
            data={
                "adapter": adapter,
                "status": "not_implemented",
                "message": (
                    f"Adapter '{adapter}' ainda nao implementado. "
                    "Sera ligado em onda futura."
                ),
            },
            status_hint="em breve",
        )

    async def _execute_serasa_pj(self, ctx: NodeContext) -> NodeOutput:
        """Dispara consulta Serasa PJ e devolve metadados pra downstream.

        Output expoe `consulta_id` — nodes seguintes (agentes
        especialistas, regras de risco) leem do warehouse via esse id.
        """
        cnpj = self.config["entity_ref"]
        environment = Environment(self.config.get("environment", "production"))

        summary = await execute_serasa_pj_query(
            tenant_id=ctx.tenant_id,
            cnpj=cnpj,
            triggered_by=f"workflow_run:{ctx.run_id}",
            environment=environment,
        )

        if not summary["ok"]:
            errors = "; ".join(summary.get("errors", []))
            raise RuntimeError(
                f"bureau_query[serasa_pj]: consulta nao concluiu — {errors}"
            )

        return NodeOutput(
            data={
                "adapter": "serasa_pj",
                "status": "ok",
                "raw_id": str(summary["raw_id"]),
                "consulta_id": str(summary["consulta_id"]),
                "cnpj": summary["cnpj"],
                "requested_report": summary["requested_report"],
                "actual_report_returned": summary["actual_report_returned"],
                "reciprocity_downgrade": summary["reciprocity_downgrade"],
                "latency_ms": summary["latency_ms"],
                "counts": summary["counts"],
            },
        )
