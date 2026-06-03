"""Document endpoints — ciclo do documento dirigido pelo analista.

  POST   /dossies/{id}/documents                  upload (+doc_type)
  GET    /dossies/{id}/documents                  lista
  POST   /dossies/{id}/documents/{doc}/extract    "Processar" (extracao sob demanda)
  PATCH  /dossies/{id}/documents/{doc}/extraction validar/editar campos
  DELETE /dossies/{id}/documents/{doc}            remover

Guardados por require_module(Module.CREDITO, ...).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.enums import DocumentType, Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.credito.schemas.document import DocumentRead, ExtractionUpdate
from app.modules.credito.services import document as document_svc
from app.modules.credito.services.document import DocumentServiceError

router = APIRouter()


def _service_error(exc: DocumentServiceError) -> HTTPException:
    msg = str(exc)
    code = 404 if "nao encontrado" in msg else 400
    return HTTPException(status_code=code, detail=msg)


@router.get("/dossies/{dossier_id}/documents", response_model=list[DocumentRead])
async def list_documents(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> list[DocumentRead]:
    rows = await document_svc.list_documents(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )
    return [DocumentRead.model_validate(r) for r in rows]


@router.post(
    "/dossies/{dossier_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
    doc_type: Annotated[DocumentType, Form(...)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> DocumentRead:
    settings = get_settings()
    body = await file.read()
    if len(body) > settings.DOSSIER_ATTACHMENT_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Arquivo grande demais ({len(body)} bytes; "
                f"max {settings.DOSSIER_ATTACHMENT_MAX_BYTES})."
            ),
        )
    try:
        doc = await document_svc.create_document(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            doc_type=doc_type,
            filename=file.filename or "documento.bin",
            mime_type=file.content_type or "application/octet-stream",
            body=body,
            uploaded_by=principal.user_id,
        )
    except DocumentServiceError as e:
        raise _service_error(e) from e
    await db.commit()
    return DocumentRead.model_validate(doc)


@router.post(
    "/dossies/{dossier_id}/documents/{document_id}/extract",
    response_model=DocumentRead,
)
async def extract_document(
    dossier_id: UUID,
    document_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> DocumentRead:
    """Dispara a extracao multimodal (o "Processar"). Reprocessar = chamar de novo."""
    doc = await document_svc.get_document(
        db,
        tenant_id=principal.tenant_id,
        dossier_id=dossier_id,
        document_id=document_id,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento nao encontrado.")
    try:
        doc = await document_svc.process_document(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            document=doc,
            initiated_by=principal.user_id,
        )
    except DocumentServiceError as e:
        # Extracao ja gravou status=error + error detail; persiste e devolve 502.
        await db.commit()
        raise HTTPException(status_code=502, detail=str(e)) from e
    await db.commit()
    return DocumentRead.model_validate(doc)


@router.get("/dossies/{dossier_id}/documents/{document_id}/file")
async def get_document_file(
    dossier_id: UUID,
    document_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> FileResponse:
    """Serve o arquivo original do documento (inline) — "Ver documento".

    Escopado por tenant via get_document; o path e resolvido com guarda
    anti path-escape (resolve_storage_path).
    """
    doc = await document_svc.get_document(
        db,
        tenant_id=principal.tenant_id,
        dossier_id=dossier_id,
        document_id=document_id,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento nao encontrado.")
    try:
        path = document_svc.resolve_storage_path(doc)
    except DocumentServiceError as e:
        raise _service_error(e) from e
    if not path.exists():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado no storage.")
    return FileResponse(
        path,
        media_type=doc.mime_type or "application/octet-stream",
        filename=doc.original_filename,
        content_disposition_type="inline",
    )


@router.patch(
    "/dossies/{dossier_id}/documents/{document_id}/extraction",
    response_model=DocumentRead,
)
async def update_document_extraction(
    dossier_id: UUID,
    document_id: UUID,
    payload: ExtractionUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> DocumentRead:
    """Analista valida/edita os campos extraidos — vira a verdade do dossie."""
    doc = await document_svc.get_document(
        db,
        tenant_id=principal.tenant_id,
        dossier_id=dossier_id,
        document_id=document_id,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento nao encontrado.")
    doc = await document_svc.update_extraction(
        db,
        tenant_id=principal.tenant_id,
        dossier_id=dossier_id,
        document=doc,
        extracted_fields=payload.extracted_fields,
        confidence=payload.confidence,
    )
    await db.commit()
    return DocumentRead.model_validate(doc)


@router.delete(
    "/dossies/{dossier_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    dossier_id: UUID,
    document_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> None:
    ok = await document_svc.delete_document(
        db,
        tenant_id=principal.tenant_id,
        dossier_id=dossier_id,
        document_id=document_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Documento nao encontrado.")
    await db.commit()
