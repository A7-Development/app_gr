"""TriggerNode — entry point of a workflow run.

This is essentially a no-op node that exists so the graph has a clear root.
Its only purpose is to materialize the trigger payload as the first node's
output, making it available to downstream nodes via `{{node.<trigger_id>.output}}`.

Config schema:
    {} (no required fields)
    Optional:
        "kind": "manual" | "api" | "schedule"  (informational only)
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.playbooks.nodes._base import (
    BaseNode,
    NodeContext,
    NodeOutput,
    VarType,
)


class TriggerNode(BaseNode):
    """Pass-through node that exposes the trigger payload as output."""

    type = "trigger"

    def produces(self) -> dict[str, VarType]:
        """Campos canônicos que `dossier_svc.create_dossier` injeta no
        `trigger_data`. Há aliases (cnpj == target_cnpj) — declaramos os
        dois para que `{{trigger.cnpj}}` e `{{trigger.target_cnpj}}` ambos
        validem.

        Quando o dossier é criado SEM CNPJ (fluxo PF ou genérico), os
        templates `{{trigger.cnpj}}` resolvem pra null em runtime — o
        validador estático só pode checar TIPO, não presença.
        """
        return {
            "dossier_id": VarType.UUID_T,
            "target_cnpj": VarType.CNPJ,
            "cnpj": VarType.CNPJ,
            "target_name": VarType.STRING,
            "trigger_kind": VarType.STRING,
        }

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        return NodeOutput(
            data={
                "trigger_kind": self.config.get("kind", "manual"),
                **ctx.trigger_data,
            },
            status_hint="Iniciado",
        )
