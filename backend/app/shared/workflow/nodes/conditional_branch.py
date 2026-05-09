"""ConditionalBranchNode — evaluates an expression and exposes the result.

The branching itself happens at the EDGE level — outgoing edges have
`condition` strings like `{{node.<this_id>.output.result}} == true`. The
engine evaluates each edge condition and skips downstream nodes whose
edges are blocked.

This node simply takes a boolean expression in its config (with template
support) and returns `{"result": bool}` plus the operands for debugging.

Config schema:
    {
        "expression": "{{node.score.output.value}} >= 700"
    }

Output:
    {"result": bool, "expression": "...", "evaluated": "..."}
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.workflow.nodes._base import BaseNode, NodeContext, NodeOutput
from app.shared.workflow.services.resolver import evaluate_edge_condition


class ConditionalBranchNode(BaseNode):
    """Evaluates a boolean expression for downstream edge routing."""

    type = "conditional_branch"

    def validate_config(self) -> None:
        if not self.config.get("expression"):
            raise ValueError(
                "conditional_branch: `config.expression` is required "
                "(e.g. '{{node.score.output.value}} >= 700')"
            )

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        # Templates in `expression` were already resolved by the engine
        # when it created `self.config` (see engine._execute_node). So at
        # this point the expression is the literal string after substitution.
        # We delegate to evaluate_edge_condition (already handles literal
        # comparisons after templating).
        expression = self.config["expression"]
        # Empty context: templates were already resolved upstream — we just
        # parse the comparison.
        result = evaluate_edge_condition(expression, {})
        return NodeOutput(
            data={
                "result": result,
                "expression": expression,
            },
            status_hint=f"resultado: {result}",
        )
