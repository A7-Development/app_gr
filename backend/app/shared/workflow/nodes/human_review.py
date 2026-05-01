"""HumanReviewNode — pauses for analyst to validate prior agent outputs.

Used after specialist agents and cross-reference complete, before opinion
generation. The analyst can edit/accept/reject the agent outputs in the UI.

Behavior:
- First execution: pauses with WAITING_INPUT.
- Resume: when analyst clicks "Aprovar e gerar parecer" in the UI, the API
  calls `engine.resume_run()` with `{"approved": True}` (and optionally
  edits to specific node outputs). The node then completes and the engine
  proceeds to the next node (typically opinion).

Config schema:
    {
        "scope": "all_analyses" | ["node_id_1", "node_id_2"]  # optional
    }
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.workflow.nodes._base import BaseNode, NodeContext, NodeOutput


class HumanReviewNode(BaseNode):
    """Pauses for analyst review before continuing."""

    type = "human_review"

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        pending = ctx.previous_outputs.get(ctx.node_id, {}).get("pending_input")
        if pending is None:
            return NodeOutput(
                data={
                    "scope": self.config.get("scope", "all_analyses"),
                    "instruction": (
                        "Revise as analises das secoes anteriores. "
                        "Aceite ou ajuste antes de gerar o parecer."
                    ),
                },
                should_pause=True,
                status_hint="Aguardando revisao do analista",
            )
        return NodeOutput(
            data={
                "approved": pending.get("approved", True),
                "analyst_overrides": pending.get("analyst_overrides", {}),
                "notes": pending.get("notes", ""),
            },
            status_hint="Revisao concluida",
        )
