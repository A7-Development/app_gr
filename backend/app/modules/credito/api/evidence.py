"""Evidence endpoints under /credito/dossies/{id}/{attachments,notes,links}.

Plus the auto-save endpoint for paused human_input nodes (PATCH /draft).
All endpoints are guarded by `require_module(Module.CREDITO, ...)`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.credito.schemas.evidence import (
    AttachmentRead,
    LinkCreate,
    LinkRead,
    NodeDraftPayload,
    NodeDraftResponse,
    NoteCreate,
    NoteRead,
    NoteUpdate,
)
from app.modules.credito.services import evidence as evidence_svc
from app.modules.credito.services.evidence import EvidenceServiceError
from app.shared.identity.user_permission import UserModulePermission

router = APIRouter()


async def _is_credito_admin(db: AsyncSession, *, user_id: UUID) -> bool:
    """Check whether the user has Permission.ADMIN in the CREDITO module."""
    perm = (
        await db.execute(
            select(UserModulePermission).where(
                UserModulePermission.user_id == user_id,
                UserModulePermission.module == Module.CREDITO,
            )
        )
    ).scalar_one_or_none()
    return perm is not None and perm.permission == Permission.ADMIN


def _service_error(exc: EvidenceServiceError) -> HTTPException:
    msg = str(exc)
    if msg.startswith("Forbidden"):
        return HTTPException(status_code=403, detail=msg)
    if msg.endswith("not found.") or "not found" in msg:
        return HTTPException(status_code=404, detail=msg)
    return HTTPException(status_code=400, detail=msg)


# ─── Attachments ─────────────────────────────────────────────────────────────


@router.get(
    "/dossies/{dossier_id}/attachments",
    response_model=list[AttachmentRead],
)
async def list_attachments(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
    node_id: str | None = None,
) -> list[AttachmentRead]:
    try:
        rows = await evidence_svc.list_attachments(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            node_id=node_id,
        )
    except EvidenceServiceError as e:
        raise _service_error(e) from e
    return [AttachmentRead.model_validate(r) for r in rows]


@router.post(
    "/dossies/{dossier_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
    node_id: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
) -> AttachmentRead:
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
        attachment = await evidence_svc.create_attachment(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            node_id=node_id,
            filename=file.filename or "file.bin",
            mime_type=file.content_type or "application/octet-stream",
            body=body,
            description=description,
            uploaded_by=principal.user_id,
        )
    except EvidenceServiceError as e:
        raise _service_error(e) from e
    await db.commit()
    return AttachmentRead.model_validate(attachment)


@router.get("/dossies/{dossier_id}/attachments/{attachment_id}/download")
async def download_attachment(
    dossier_id: UUID,
    attachment_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> StreamingResponse:
    attachment = await evidence_svc.get_attachment(
        db,
        tenant_id=principal.tenant_id,
        dossier_id=dossier_id,
        attachment_id=attachment_id,
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="Anexo nao encontrado.")

    try:
        handle = evidence_svc.open_attachment_blob(attachment)
    except EvidenceServiceError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    def iterator():
        try:
            while chunk := handle.read(64 * 1024):
                yield chunk
        finally:
            handle.close()

    safe_name = attachment.filename.replace('"', "_")
    return StreamingResponse(
        iterator(),
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Content-Length": str(attachment.size_bytes),
        },
    )


@router.delete(
    "/dossies/{dossier_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_attachment(
    dossier_id: UUID,
    attachment_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> None:
    try:
        await evidence_svc.delete_attachment(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            attachment_id=attachment_id,
            requester_id=principal.user_id,
            requester_is_admin=await _is_credito_admin(db, user_id=principal.user_id),
        )
    except EvidenceServiceError as e:
        raise _service_error(e) from e
    await db.commit()


# ─── Step notes ─────────────────────────────────────────────────────────────


@router.get(
    "/dossies/{dossier_id}/notes",
    response_model=list[NoteRead],
)
async def list_notes(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
    node_id: str | None = None,
) -> list[NoteRead]:
    try:
        rows = await evidence_svc.list_notes(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            node_id=node_id,
        )
    except EvidenceServiceError as e:
        raise _service_error(e) from e
    return [NoteRead.model_validate(r) for r in rows]


@router.post(
    "/dossies/{dossier_id}/notes",
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_note(
    dossier_id: UUID,
    payload: NoteCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> NoteRead:
    try:
        note = await evidence_svc.create_note(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            node_id=payload.node_id,
            body_md=payload.body_md,
            pinned=payload.pinned,
            author_id=principal.user_id,
        )
    except EvidenceServiceError as e:
        raise _service_error(e) from e
    await db.commit()
    return NoteRead.model_validate(note)


@router.patch(
    "/dossies/{dossier_id}/notes/{note_id}",
    response_model=NoteRead,
)
async def update_note(
    dossier_id: UUID,
    note_id: UUID,
    payload: NoteUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> NoteRead:
    try:
        note = await evidence_svc.update_note(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            note_id=note_id,
            requester_id=principal.user_id,
            body_md=payload.body_md,
            pinned=payload.pinned,
        )
    except EvidenceServiceError as e:
        raise _service_error(e) from e
    await db.commit()
    return NoteRead.model_validate(note)


@router.delete(
    "/dossies/{dossier_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_note(
    dossier_id: UUID,
    note_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> None:
    try:
        await evidence_svc.delete_note(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            note_id=note_id,
            requester_id=principal.user_id,
            requester_is_admin=await _is_credito_admin(db, user_id=principal.user_id),
        )
    except EvidenceServiceError as e:
        raise _service_error(e) from e
    await db.commit()


# ─── Step links ─────────────────────────────────────────────────────────────


@router.get(
    "/dossies/{dossier_id}/links",
    response_model=list[LinkRead],
)
async def list_links(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
    node_id: str | None = None,
) -> list[LinkRead]:
    try:
        rows = await evidence_svc.list_links(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            node_id=node_id,
        )
    except EvidenceServiceError as e:
        raise _service_error(e) from e
    return [LinkRead.model_validate(r) for r in rows]


@router.post(
    "/dossies/{dossier_id}/links",
    response_model=LinkRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_link(
    dossier_id: UUID,
    payload: LinkCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> LinkRead:
    try:
        link = await evidence_svc.create_link(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            node_id=payload.node_id,
            url=str(payload.url),
            title=payload.title,
            description=payload.description,
            added_by=principal.user_id,
        )
    except EvidenceServiceError as e:
        raise _service_error(e) from e
    await db.commit()
    return LinkRead.model_validate(link)


@router.delete(
    "/dossies/{dossier_id}/links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_link(
    dossier_id: UUID,
    link_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> None:
    try:
        await evidence_svc.delete_link(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            link_id=link_id,
            requester_id=principal.user_id,
            requester_is_admin=await _is_credito_admin(db, user_id=principal.user_id),
        )
    except EvidenceServiceError as e:
        raise _service_error(e) from e
    await db.commit()


# ─── Draft auto-save ────────────────────────────────────────────────────────


@router.patch(
    "/dossies/{dossier_id}/nodes/{node_id}/draft",
    response_model=NodeDraftResponse,
)
async def save_node_draft(
    dossier_id: UUID,
    node_id: str,
    payload: NodeDraftPayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> NodeDraftResponse:
    """Persist partial form values for a paused human_input node.

    Does NOT advance the workflow — POST .../submit remains the explicit
    progression. Returns the saved_at timestamp the SaveIndicator UI uses.
    """
    try:
        saved_at = await evidence_svc.save_node_draft(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            node_id=node_id,
            values=dict(payload.values),
        )
    except EvidenceServiceError as e:
        raise _service_error(e) from e
    await db.commit()
    return NodeDraftResponse(saved_at=saved_at, node_id=node_id)
