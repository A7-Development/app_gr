"""SpecialistAgentNode — runs an IA specialist agent (catalog-driven).

This is the integration point with `app.shared.agents.runtime`. The node's
config picks an agent by name; the runtime resolves the agent spec from
the catalog (system prompt versioned in `ai_prompt`, allowed tools,
output schema), invokes Claude via `claude-agent-sdk`, validates the
output, and returns it.

Config schema:
    {
        "agent": "social_contract_analyst" | "financial_analyst" | ...
    }

The agent name MUST exist in `app.shared.agents.catalog.CATALOG`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.workflow.nodes._base import BaseNode, NodeContext, NodeOutput


class SpecialistAgentNode(BaseNode):
    """Runs a SpecialistAgent from the catalog."""

    type = "specialist_agent"

    def validate_config(self) -> None:
        agent_name = self.config.get("agent")
        if not agent_name:
            raise ValueError(
                "specialist_agent node requires `config.agent` "
                "(name of a registered SpecialistAgentSpec)"
            )
        # Late import to avoid circular ref at module load:
        from app.shared.agents.catalog import CATALOG

        if agent_name not in CATALOG:
            raise ValueError(
                f"specialist_agent: unknown agent '{agent_name}'. "
                f"Available: {sorted(CATALOG.keys())}"
            )

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        from app.shared.agents.catalog import CATALOG
        from app.shared.agents.runtime import run_specialist_agent

        spec = CATALOG[self.config["agent"]]
        result = await run_specialist_agent(
            spec=spec,
            ctx=ctx,
            db=db,
        )
        return NodeOutput(
            data=result.output_data,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            cost_brl=result.cost_brl,
            status_hint=f"Agente {spec.name} concluido",
        )
