"""Document tools — agent access to extracted documents data.

Tools:
- get_document_extraction(doc_type) — returns the structured ai_extraction
  field of the most recent doc of the given type for this dossier
- list_documents_in_section(section) — lists docs for the given section
  (free-form section -> doc_type mapping owned by the credito module)
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.agents.tools._base import AgentTool


def make_document_tools(
    tenant_id: UUID,
    dossier_id: UUID,
    db: AsyncSession,
) -> list[AgentTool]:
    """Build a list of AgentTool instances for document access."""

    async def _get_document_extraction(args: dict[str, Any]) -> str:
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
            return f"Nenhum documento do tipo '{doc_type}' foi extraido ainda."
        return json.dumps(
            {
                "doc_type": doc_type,
                "uploaded_at": row.uploaded_at.isoformat(),
                "extraction": row.ai_extraction,
            },
            ensure_ascii=False,
        )

    async def _list_documents_in_section(args: dict[str, Any]) -> str:
        from app.modules.credito.models.document import CreditDossierDocument

        # `section` chega no payload mas hoje a tabela nao tem coluna de
        # secao explicita — seguimos retornando todos os documentos do
        # dossie. Mantido na assinatura por compatibilidade com prompts
        # que ja referenciam o argumento.
        _ = args.get("section")

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
                "doc_type": (
                    r.doc_type.value if hasattr(r.doc_type, "value") else str(r.doc_type)
                ),
                "filename": r.original_filename,
                "extracted": r.ai_extraction is not None,
                "uploaded_at": r.uploaded_at.isoformat(),
            }
            for r in rows
        ]
        return json.dumps(items, ensure_ascii=False)

    return [
        AgentTool(
            name="get_document_extraction",
            description=(
                "Retorna a extracao estruturada (ai_extraction) do documento "
                "mais recente de um dado tipo. Tipos validos incluem 'dre', "
                "'balance_sheet', 'social_contract', 'income_tax_pf', "
                "'commercial_visit', 'scr', etc."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "doc_type": {
                        "type": "string",
                        "description": "Tipo do documento (lowercase).",
                    }
                },
                "required": ["doc_type"],
                "additionalProperties": False,
            },
            handler=_get_document_extraction,
        ),
        AgentTool(
            name="list_documents_in_section",
            description=(
                "Lista documentos enviados ao dossie. Retorna doc_type + "
                "filename + status de extracao para cada um. O argumento "
                "`section` e mantido por compatibilidade mas nao restringe "
                "o resultado hoje (a tabela nao tem coluna de secao)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "description": "Nome da secao (compatibilidade — ignorado).",
                    }
                },
                "required": ["section"],
                "additionalProperties": False,
            },
            handler=_list_documents_in_section,
        ),
    ]
