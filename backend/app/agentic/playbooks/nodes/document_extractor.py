"""DocumentExtractorNode — extracts structured data from uploaded documents.

For each unprocessed document linked to the dossier, invokes the
`document_extractor` specialist agent (Claude Vision multimodal) with the
appropriate `extract.<doc_type>` prompt. Persists the structured result on
`credit_dossier_document.ai_extraction`.

Config schema:
    {
        "for_each": "uploaded_documents",   # required, only value supported in MVP
        "agent": "document_extractor"       # required, must exist in CATALOG
    }
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.playbooks.nodes._base import BaseNode, NodeContext, NodeOutput


class DocumentExtractorNode(BaseNode):
    """Iterates over uploaded documents, extracting each via specialist agent."""

    type = "document_extractor"

    def validate_config(self) -> None:
        if self.config.get("for_each") != "uploaded_documents":
            raise ValueError(
                "document_extractor: only `for_each: uploaded_documents` "
                "is supported in the MVP."
            )
        if not self.config.get("agent"):
            raise ValueError("document_extractor: `config.agent` is required.")

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        # Late import to avoid circular reference.
        from app.agentic.engine.catalog import CATALOG
        from app.agentic.engine.runtime import run_document_extraction
        from app.modules.credito.models.document import CreditDossierDocument

        dossier_id = ctx.trigger_data.get("dossier_id")
        if dossier_id is None:
            raise ValueError(
                "document_extractor requires trigger_data.dossier_id."
            )

        agent_spec = CATALOG.get(self.config["agent"])
        if agent_spec is None:
            raise ValueError(
                f"document_extractor: agent '{self.config['agent']}' not found in catalog."
            )

        # Find unprocessed documents for this dossier (no ai_extraction yet).
        rows = (
            await db.execute(
                select(CreditDossierDocument).where(
                    CreditDossierDocument.tenant_id == ctx.tenant_id,
                    CreditDossierDocument.dossier_id == dossier_id,
                    CreditDossierDocument.ai_extraction.is_(None),
                )
            )
        ).scalars().all()

        results: list[dict] = []
        total_input = 0
        total_output = 0
        from decimal import Decimal

        total_cost = Decimal("0")

        for doc in rows:
            try:
                extraction = await run_document_extraction(
                    spec=agent_spec,
                    document=doc,
                    ctx=ctx,
                    db=db,
                )
                results.append({
                    "document_id": str(doc.id),
                    "doc_type": doc.doc_type.value if hasattr(doc.doc_type, "value") else str(doc.doc_type),
                    "status": "ok",
                })
                total_input += extraction.tokens_input
                total_output += extraction.tokens_output
                total_cost += extraction.cost_brl
            except Exception as e:
                results.append({
                    "document_id": str(doc.id),
                    "status": "error",
                    "error": str(e),
                })

        return NodeOutput(
            data={
                "documents_processed": len(results),
                "results": results,
            },
            tokens_input=total_input,
            tokens_output=total_output,
            cost_brl=total_cost,
            status_hint=f"{len(results)} documentos processados",
        )
