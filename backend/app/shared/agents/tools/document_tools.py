"""Document tools — agent access to extracted documents data.

Tools:
- get_document_extraction(doc_type) — returns the structured ai_extraction
  field of the most recent doc of the given type for this dossier
- list_documents_in_section(section) — lists docs that belong to a given
  section (free-form section -> doc_type mapping owned by the credito module)
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from claude_agent_sdk import tool
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession


def make_document_tools(
    tenant_id: UUID,
    dossier_id: UUID,
    db: AsyncSession,
) -> list:
    """Build a list of tool callables for document access."""

    @tool(
        "get_document_extraction",
        "Retorna a extracao estruturada (ai_extraction) do documento mais "
        "recente de um dado tipo. Tipos validos incluem 'dre', 'balance_sheet', "
        "'social_contract', 'income_tax_pf', 'commercial_visit', 'scr', etc.",
        {"doc_type": str},
    )
    async def get_document_extraction(args: dict[str, Any]) -> dict[str, Any]:
        from app.modules.credito.models.document import CreditDossierDocument

        doc_type = args["doc_type"].lower()
        row = (
            await db.execute(
                select(CreditDossierDocument)
                .where(
                    CreditDossierDocument.tenant_id == tenant_id,
                    CreditDossierDocument.dossier_id == dossier_id,
                    CreditDossierDocument.doc_type == doc_type,
                    CreditDossierDocument.ai_extraction.isnot(None),
                )
                .order_by(desc(CreditDossierDocument.uploaded_at))
                .limit(1)
            )
        ).scalar_one_or_none()

        if row is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Nenhum documento do tipo '{doc_type}' foi extraido ainda.",
                    }
                ]
            }
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "doc_type": doc_type,
                            "uploaded_at": row.uploaded_at.isoformat(),
                            "extraction": row.ai_extraction,
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        }

    @tool(
        "list_documents_in_section",
        "Lista todos os documentos enviados de uma secao do dossie. "
        "Retorna doc_type + filename + status de extracao para cada um.",
        {"section": str},
    )
    async def list_documents_in_section(args: dict[str, Any]) -> dict[str, Any]:
        from app.modules.credito.models.document import CreditDossierDocument

        rows = (
            await db.execute(
                select(CreditDossierDocument).where(
                    CreditDossierDocument.tenant_id == tenant_id,
                    CreditDossierDocument.dossier_id == dossier_id,
                )
            )
        ).scalars().all()
        items = [
            {
                "id": str(r.id),
                "doc_type": r.doc_type.value if hasattr(r.doc_type, "value") else str(r.doc_type),
                "filename": r.original_filename,
                "extracted": r.ai_extraction is not None,
                "uploaded_at": r.uploaded_at.isoformat(),
            }
            for r in rows
        ]
        return {
            "content": [{"type": "text", "text": json.dumps(items, ensure_ascii=False)}]
        }

    return [get_document_extraction, list_documents_in_section]
