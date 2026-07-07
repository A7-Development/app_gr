"""OutputGeneratorNode — produces the final dossier artifact (PDF/JSON).

Final node of the credit workflow. In MVP this generates a basic PDF
summarizing the dossier from agent outputs and analyst notes.

Config schema:
    {
        "format": "pdf" | "json"
    }
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.workflows.nodes._base import BaseNode, NodeContext, NodeOutput


class OutputGeneratorNode(BaseNode):
    """Generates the final dossier output (PDF/JSON)."""

    type = "output_generator"

    def validate_config(self) -> None:
        fmt = self.config.get("format", "pdf")
        if fmt not in {"pdf", "json"}:
            raise ValueError(
                f"output_generator: unsupported format '{fmt}'. Use 'pdf' or 'json'."
            )

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        # Late import — credito module owns the PDF generator.
        from app.modules.credito.services.pdf_generator import generate_dossier_artifact

        dossier_id = ctx.trigger_data.get("dossier_id")
        if dossier_id is None:
            raise ValueError("output_generator requires trigger_data.dossier_id.")

        fmt = self.config.get("format", "pdf")
        artifact = await generate_dossier_artifact(
            dossier_id=dossier_id,
            tenant_id=ctx.tenant_id,
            previous_outputs=ctx.previous_outputs,
            output_format=fmt,
            db=db,
        )

        return NodeOutput(
            data=artifact,
            status_hint=f"Output gerado ({fmt})",
        )
