"""SpecialistAgentNode — runs an IA specialist agent (catalog-driven).

This is the integration point with `app.shared.agents.runtime`. The node's
config picks an agent by name; the runtime resolves the agent spec from
the catalog (system prompt versioned in `ai_prompt`, allowed tools,
output schema), invokes Claude via the Anthropic Messages API (official
`anthropic` SDK with native tool use), validates the output, and returns it.

Config schema:
    {
        "agent": "social_contract_analyst" | "financial_analyst" | ...
    }

The agent name MUST exist in `app.shared.agents.catalog.CATALOG`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.workflow.nodes._base import (
    BaseNode,
    NodeContext,
    NodeOutput,
    VarType,
)


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

    def produces(self) -> dict[str, VarType]:
        """O output do agente é um Pydantic model serializado em dict.

        Para o validador estático, expomos os top-level fields do schema
        com tipos pragmáticos: bools como BOOLEAN, lists como LIST, demais
        como OBJECT. Quem consumir downstream em geral acessa via tool no
        próprio agente seguinte (read_dossier_section), não por templates
        — então essa declaração é informativa.
        """
        agent_name = self.config.get("agent")
        if not agent_name:
            return {}
        try:
            from app.shared.agents.catalog import CATALOG
        except ImportError:
            return {}
        spec = CATALOG.get(agent_name)
        if spec is None:
            return {}
        out: dict[str, VarType] = {}
        for fname, finfo in spec.output_schema.model_fields.items():
            ann = finfo.annotation
            type_str = str(ann).lower()
            if "bool" in type_str:
                out[fname] = VarType.BOOLEAN
            elif "list" in type_str or "tuple" in type_str:
                out[fname] = VarType.LIST
            elif "int" in type_str or "float" in type_str or "decimal" in type_str:
                out[fname] = VarType.NUMBER
            elif "str" in type_str:
                out[fname] = VarType.STRING
            else:
                out[fname] = VarType.OBJECT
        return out

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
