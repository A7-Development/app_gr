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

from app.shared.workflow.nodes._base import BaseNode, NodeContext, NodeOutput


class TriggerNode(BaseNode):
    """Pass-through node that exposes the trigger payload as output."""

    type = "trigger"

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        return NodeOutput(
            data={
                "trigger_kind": self.config.get("kind", "manual"),
                **ctx.trigger_data,
            },
            status_hint="Iniciado",
        )
