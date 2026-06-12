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
        """O gatilho e MINIMO por decisao de produto (2026-06-12, Ricardo):
        publica so a identidade da analise (dossier_id) + o tipo de abertura.

        A identidade da EMPRESA (CNPJ/razao social) NAO e variavel de gatilho:
        entra pelo formulario de Identificacao (human_input -> absorb_identity)
        e materializa na empresa-alvo do DOSSIE — nodes de fonte oficial
        (cadastral, JUCESP) leem de la. CNPJ informado na abertura vira apenas
        pre-preenchimento do formulario. Legado {{trigger.cnpj}} removido com
        zero dossies reais na plataforma.
        """
        return {
            "dossier_id": VarType.UUID_T,
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
