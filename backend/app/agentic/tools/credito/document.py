"""Tools de acesso a documentos extraidos do dossie de credito.

Tools registradas:
- get_document_extraction(doc_type) — ai_extraction do doc mais recente
- list_documents_in_section(section) — lista docs do dossie

Antes (F0): factory `make_document_tools(tenant_id, dossier_id, db)` com
closure. Apos F2.a: tools recebem `ScopedContext` em runtime.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, select

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission


@register_tool(
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
    module=Module.CREDITO,
    min_permission=Permission.READ,
    cost_hint="cheap",
)
async def get_document_extraction(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Retorna extracao do documento mais recente do tipo no dossie ativo."""
    from app.modules.credito.models.document import CreditDossierDocument

    doc_type = args["doc_type"].lower()
    dossier_id = scope.extras["dossier_id"]

    row = (
        await scope.db.execute(
            select(CreditDossierDocument)
            .where(
                CreditDossierDocument.tenant_id == scope.tenant_id,
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


@register_tool(
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
    module=Module.CREDITO,
    min_permission=Permission.READ,
    cost_hint="cheap",
)
async def list_documents_in_section(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Lista documentos do dossie ativo (argumento `section` ignorado hoje)."""
    from app.modules.credito.models.document import CreditDossierDocument

    # `section` chega no payload mas hoje a tabela nao tem coluna de
    # secao explicita — seguimos retornando todos os documentos do
    # dossie. Mantido na assinatura por compatibilidade com prompts
    # que ja referenciam o argumento.
    _ = args.get("section")

    dossier_id = scope.extras["dossier_id"]

    rows = (
        await scope.db.execute(
            select(CreditDossierDocument).where(
                CreditDossierDocument.tenant_id == scope.tenant_id,
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
