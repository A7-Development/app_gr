"""DocumentRequestNode — pauses workflow waiting for analyst to upload documents.

Defines a list of required and optional document types. The node stays in
WAITING_INPUT until at least all required types have been uploaded for the
current dossier (queried via `credit_dossier_document` linked by trigger_data.dossier_id).

Config schema:
    {
        "required": ["DRE", "BALANCE_SHEET", "REVENUE_REPORT", "SOCIAL_CONTRACT"],
        "optional": ["INCOME_TAX_PF", "CNH", "COMMERCIAL_VISIT", "PHOTO", "ABC_CURVE", "SCR"]
    }

(Values match `app.core.enums.DocumentType` keys, uppercase.)
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.playbooks.nodes._base import BaseNode, NodeContext, NodeOutput
from app.core.enums import DocumentType


class DocumentRequestNode(BaseNode):
    """Pauses until required documents have been uploaded."""

    type = "document_request"

    def validate_config(self) -> None:
        required = self.config.get("required", [])
        if not isinstance(required, list):
            raise ValueError("document_request node: `config.required` must be a list")
        for item in required:
            if item.lower() not in {dt.value for dt in DocumentType}:
                raise ValueError(
                    f"document_request: unknown DocumentType '{item}' in `required`. "
                    f"Valid: {sorted({dt.value for dt in DocumentType})}"
                )

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        # Late import to avoid circular: credito module imports workflow public.
        from app.modules.credito.models.document import CreditDossierDocument

        dossier_id = ctx.trigger_data.get("dossier_id")
        if dossier_id is None:
            raise ValueError(
                "document_request node requires trigger_data.dossier_id "
                "(this workflow must be initiated from a credit dossier)."
            )

        required = [r.lower() for r in self.config.get("required", [])]
        optional = [o.lower() for o in self.config.get("optional", [])]

        rows = (
            await db.execute(
                select(CreditDossierDocument.doc_type).where(
                    CreditDossierDocument.tenant_id == ctx.tenant_id,
                    CreditDossierDocument.dossier_id == dossier_id,
                )
            )
        ).scalars().all()
        uploaded = {r.value if hasattr(r, "value") else str(r) for r in rows}

        missing = [r for r in required if r not in uploaded]

        if missing:
            return NodeOutput(
                data={
                    "required": required,
                    "optional": optional,
                    "uploaded": sorted(uploaded),
                    "missing": missing,
                },
                should_pause=True,
                status_hint=f"Faltam documentos obrigatorios: {len(missing)}",
            )

        return NodeOutput(
            data={
                "required": required,
                "optional": optional,
                "uploaded": sorted(uploaded),
                "missing": [],
            },
            status_hint="Documentos obrigatorios recebidos",
        )
