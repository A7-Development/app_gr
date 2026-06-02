"""Document service — ciclo do documento dirigido pelo analista.

Fluxo (handoff esteira-credito): upload(+doc_type) -> "Processar" (extracao
multimodal sob demanda) -> validar/editar -> reprocessar. O arquivo vive no
mesmo storage dos anexos (DOSSIER_STORAGE_ROOT); a extracao reusa o pipeline
multimodal (run_document_extraction). Tudo escopado por tenant_id.

NOTA: a persistencia nas tabelas canonicas estruturadas (DRE/balanco/etc) e a
proxima fatia — aqui o resultado da extracao fica no JSONB ai_extraction.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import DocumentType
from app.modules.credito.models.document import CreditDossierDocument
from app.modules.credito.models.dossier import CreditDossier


class DocumentServiceError(RuntimeError):
    """Domain-level document error."""


def _storage_root() -> Path:
    return Path(get_settings().DOSSIER_STORAGE_ROOT).resolve()


async def _ensure_dossier(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> CreditDossier:
    dossier = (
        await db.execute(
            select(CreditDossier).where(
                CreditDossier.tenant_id == tenant_id,
                CreditDossier.id == dossier_id,
            )
        )
    ).scalar_one_or_none()
    if dossier is None:
        raise DocumentServiceError(f"Dossie {dossier_id} nao encontrado.")
    return dossier


async def get_document(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID, document_id: UUID
) -> CreditDossierDocument | None:
    return (
        await db.execute(
            select(CreditDossierDocument).where(
                CreditDossierDocument.tenant_id == tenant_id,
                CreditDossierDocument.dossier_id == dossier_id,
                CreditDossierDocument.id == document_id,
            )
        )
    ).scalar_one_or_none()


async def list_documents(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> list[CreditDossierDocument]:
    rows = (
        await db.execute(
            select(CreditDossierDocument)
            .where(
                CreditDossierDocument.tenant_id == tenant_id,
                CreditDossierDocument.dossier_id == dossier_id,
            )
            .order_by(CreditDossierDocument.uploaded_at.desc())
        )
    ).scalars().all()
    return list(rows)


async def create_document(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    doc_type: DocumentType,
    filename: str,
    mime_type: str | None,
    body: bytes,
    uploaded_by: UUID | None,
) -> CreditDossierDocument:
    """Salva o arquivo + cria o registro (extraction_status=pending)."""
    if not body:
        raise DocumentServiceError("Arquivo vazio nao e permitido.")
    max_bytes = get_settings().DOSSIER_ATTACHMENT_MAX_BYTES
    if len(body) > max_bytes:
        raise DocumentServiceError(
            f"Arquivo grande demais ({len(body)} bytes; max {max_bytes})."
        )
    await _ensure_dossier(db, tenant_id=tenant_id, dossier_id=dossier_id)

    sha = hashlib.sha256(body).hexdigest()
    rel = f"{tenant_id}/{dossier_id}/documents/{sha[:2]}/{sha}"
    path = _storage_root() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(body)

    doc = CreditDossierDocument(
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        doc_type=doc_type,
        original_filename=(filename or "documento.bin")[:255],
        file_path=rel,
        file_hash_sha256=sha,
        file_size_bytes=len(body),
        mime_type=mime_type,
        uploaded_by=uploaded_by,
        extraction_status="pending",
    )
    db.add(doc)
    await db.flush()
    return doc


async def process_document(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    document: CreditDossierDocument,
    initiated_by: UUID | None,
) -> CreditDossierDocument:
    """Dispara a extracao multimodal sob demanda (o botao "Processar").

    Le o arquivo (PDF/imagem) via Claude Vision usando o prompt extract.<tipo>,
    persiste o resultado em ai_extraction. Reprocessar = chamar de novo.
    """
    # Lazy imports — runtime puxa muita coisa; evita ciclo no import tree.
    from app.agentic.engine.catalog import CATALOG
    from app.agentic.engine.runtime import run_document_extraction
    from app.agentic.playbooks.nodes._base import NodeContext

    spec = CATALOG.get("document_extractor")
    if spec is None:
        raise DocumentServiceError(
            "Agente 'document_extractor' nao encontrado no catalogo."
        )

    dossier = await _ensure_dossier(db, tenant_id=tenant_id, dossier_id=dossier_id)
    ctx = NodeContext(
        run_id=dossier.workflow_run_id or uuid4(),
        tenant_id=tenant_id,
        node_id="adhoc:document_extract",
        initiated_by=initiated_by,
        trigger_data={"dossier_id": str(dossier_id)},
    )

    document.extraction_status = "processing"
    document.extraction_error = None
    await db.flush()

    try:
        await run_document_extraction(spec=spec, document=document, ctx=ctx, db=db)
    except Exception as e:
        document.extraction_status = "error"
        document.extraction_error = str(e)[:1000]
        await db.flush()
        raise DocumentServiceError(f"Falha na extracao: {e}") from e

    # Confianca reportada pela extracao (campo `confidence` do DocumentExtraction).
    conf = (document.ai_extraction or {}).get("confidence")
    if isinstance(conf, (int, float)):
        document.extraction_confidence = Decimal(str(conf))
    document.extraction_status = "success"
    await db.flush()
    return document


async def update_extraction(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    document: CreditDossierDocument,
    extracted_fields: dict,
    confidence: float | None,
) -> CreditDossierDocument:
    """Analista valida/edita os campos extraidos — vira a verdade do dossie.

    O resultado original da IA e preservado em ai_extraction['_ai_original']
    na primeira edicao (proveniencia §14: IA opina, humano homologa).
    """
    current = dict(document.ai_extraction or {})
    if "_ai_original" not in current:
        current["_ai_original"] = current.get("extracted_fields")
    current["extracted_fields"] = extracted_fields
    current["_analyst_edited"] = True
    document.ai_extraction = current  # reatribui p/ marcar dirty no JSONB
    if confidence is not None:
        document.extraction_confidence = Decimal(str(confidence))
    document.extraction_status = "validated"
    await db.flush()
    return document


async def delete_document(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID, document_id: UUID
) -> bool:
    doc = await get_document(
        db, tenant_id=tenant_id, dossier_id=dossier_id, document_id=document_id
    )
    if doc is None:
        return False
    await db.delete(doc)
    await db.flush()
    return True


__all__ = [
    "DocumentServiceError",
    "create_document",
    "delete_document",
    "get_document",
    "list_documents",
    "process_document",
    "update_extraction",
]
