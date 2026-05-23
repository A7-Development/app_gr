"""Evidence service — CRUD for attachments, step notes, step links + draft save.

These are the per-dossier user-generated artifacts the right-rail Evidence
panel surfaces during the wizard. All operations scope by `tenant_id`.

Storage layer (attachments):
- Blobs live on the filesystem under `settings.DOSSIER_STORAGE_ROOT/{tenant_id}/
  {dossier_id}/{sha256[:2]}/{sha256}` (sharded by hash prefix).
- `sha256` dedupe: the same file uploaded twice creates 1 row on disk and 2
  rows in the table referencing it. Delete only removes the blob when no
  other attachment row in the same tenant references the same hash.
- Migration to S3 is a Phase 2 concern: swap `_save_blob_to_disk` /
  `_open_blob_from_disk` / `_delete_blob_if_unreferenced` with an S3 backend.
"""

from __future__ import annotations

import contextlib
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.playbooks.models.run import PlaybookRunStep
from app.core.config import get_settings
from app.core.enums import NodeRunStatus
from app.modules.credito.models.dossier import CreditDossier
from app.modules.credito.models.dossier_attachment import DossierAttachment
from app.modules.credito.models.dossier_step_link import DossierStepLink
from app.modules.credito.models.dossier_step_note import DossierStepNote


class EvidenceServiceError(RuntimeError):
    """Domain-level evidence error (size limit, not found, forbidden, etc)."""


# ─── Internal helpers ───────────────────────────────────────────────────────


async def _ensure_dossier_exists(
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
        raise EvidenceServiceError(f"Dossier {dossier_id} not found for tenant.")
    return dossier


def _storage_root() -> Path:
    return Path(get_settings().DOSSIER_STORAGE_ROOT).resolve()


def _blob_path(tenant_id: UUID, dossier_id: UUID, sha256: str) -> Path:
    return (
        _storage_root()
        / str(tenant_id)
        / str(dossier_id)
        / sha256[:2]
        / sha256
    )


def _save_blob_to_disk(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # Already on disk (sha dedupe); leave as-is.
        return
    path.write_bytes(body)


def _open_blob_from_disk(path: Path) -> BinaryIO:
    if not path.exists():
        raise EvidenceServiceError(f"Blob missing on disk: {path}")
    return path.open("rb")


async def _delete_blob_if_unreferenced(
    db: AsyncSession, *, tenant_id: UUID, sha256: str, path: Path
) -> None:
    refs = (
        await db.execute(
            select(func.count(DossierAttachment.id)).where(
                DossierAttachment.tenant_id == tenant_id,
                DossierAttachment.sha256 == sha256,
            )
        )
    ).scalar_one()
    if refs == 0 and path.exists():
        with contextlib.suppress(OSError):
            path.unlink()  # best-effort; file system noise is not fatal here


# ─── Attachments ────────────────────────────────────────────────────────────


async def create_attachment(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    node_id: str | None,
    filename: str,
    mime_type: str,
    body: bytes,
    description: str | None,
    uploaded_by: UUID | None,
) -> DossierAttachment:
    """Persist a file blob + create the metadata row.

    Caller (the endpoint) is responsible for enforcing size limits BEFORE
    calling this — `body` is the full file in memory. We still raise here
    if it's empty or exceeds the configured limit as a defense-in-depth.
    """
    settings = get_settings()
    max_bytes = settings.DOSSIER_ATTACHMENT_MAX_BYTES
    if len(body) == 0:
        raise EvidenceServiceError("Empty file is not allowed.")
    if len(body) > max_bytes:
        raise EvidenceServiceError(
            f"File too large ({len(body)} bytes; max {max_bytes})."
        )

    await _ensure_dossier_exists(db, tenant_id=tenant_id, dossier_id=dossier_id)

    sha256 = hashlib.sha256(body).hexdigest()
    storage_key = f"{tenant_id}/{dossier_id}/{sha256[:2]}/{sha256}"
    path = _blob_path(tenant_id, dossier_id, sha256)
    _save_blob_to_disk(path, body)

    attachment = DossierAttachment(
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        node_id=node_id or None,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(body),
        storage_key=storage_key,
        sha256=sha256,
        description=description,
        uploaded_by=uploaded_by,
    )
    db.add(attachment)
    await db.flush()
    await db.refresh(attachment)
    return attachment


async def list_attachments(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    node_id: str | None = None,
) -> list[DossierAttachment]:
    await _ensure_dossier_exists(db, tenant_id=tenant_id, dossier_id=dossier_id)
    query = select(DossierAttachment).where(
        DossierAttachment.tenant_id == tenant_id,
        DossierAttachment.dossier_id == dossier_id,
    )
    if node_id is not None:
        query = query.where(DossierAttachment.node_id == node_id)
    query = query.order_by(DossierAttachment.uploaded_at.desc())
    return list((await db.execute(query)).scalars().all())


async def get_attachment(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    attachment_id: UUID,
) -> DossierAttachment | None:
    return (
        await db.execute(
            select(DossierAttachment).where(
                DossierAttachment.tenant_id == tenant_id,
                DossierAttachment.dossier_id == dossier_id,
                DossierAttachment.id == attachment_id,
            )
        )
    ).scalar_one_or_none()


def open_attachment_blob(attachment: DossierAttachment) -> BinaryIO:
    """Return a binary file handle for streaming (caller closes)."""
    path = _blob_path(attachment.tenant_id, attachment.dossier_id, attachment.sha256)
    return _open_blob_from_disk(path)


async def delete_attachment(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    attachment_id: UUID,
    requester_id: UUID,
    requester_is_admin: bool,
) -> None:
    """Delete an attachment row + the blob if no other row references the hash.

    Only the uploader or a tenant admin can delete.
    """
    attachment = await get_attachment(
        db,
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        attachment_id=attachment_id,
    )
    if attachment is None:
        raise EvidenceServiceError("Attachment not found.")

    if attachment.uploaded_by != requester_id and not requester_is_admin:
        raise EvidenceServiceError("Forbidden — only the uploader or an admin may delete.")

    sha256 = attachment.sha256
    path = _blob_path(attachment.tenant_id, attachment.dossier_id, sha256)
    await db.delete(attachment)
    await db.flush()
    await _delete_blob_if_unreferenced(
        db, tenant_id=tenant_id, sha256=sha256, path=path
    )


# ─── Step notes ─────────────────────────────────────────────────────────────


async def create_note(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    node_id: str,
    body_md: str,
    pinned: bool,
    author_id: UUID | None,
) -> DossierStepNote:
    await _ensure_dossier_exists(db, tenant_id=tenant_id, dossier_id=dossier_id)
    note = DossierStepNote(
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        node_id=node_id,
        body_md=body_md,
        pinned=pinned,
        author_id=author_id,
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)
    return note


async def list_notes(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    node_id: str | None = None,
) -> list[DossierStepNote]:
    await _ensure_dossier_exists(db, tenant_id=tenant_id, dossier_id=dossier_id)
    query = select(DossierStepNote).where(
        DossierStepNote.tenant_id == tenant_id,
        DossierStepNote.dossier_id == dossier_id,
    )
    if node_id is not None:
        query = query.where(DossierStepNote.node_id == node_id)
    # Pinned notes float to the top, then chronological desc.
    query = query.order_by(
        DossierStepNote.pinned.desc(),
        DossierStepNote.created_at.desc(),
    )
    return list((await db.execute(query)).scalars().all())


async def get_note(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    note_id: UUID,
) -> DossierStepNote | None:
    return (
        await db.execute(
            select(DossierStepNote).where(
                DossierStepNote.tenant_id == tenant_id,
                DossierStepNote.dossier_id == dossier_id,
                DossierStepNote.id == note_id,
            )
        )
    ).scalar_one_or_none()


async def update_note(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    note_id: UUID,
    requester_id: UUID,
    body_md: str | None,
    pinned: bool | None,
) -> DossierStepNote:
    """Update note body or pin state. Only the author can edit."""
    note = await get_note(
        db, tenant_id=tenant_id, dossier_id=dossier_id, note_id=note_id
    )
    if note is None:
        raise EvidenceServiceError("Note not found.")
    if note.author_id != requester_id:
        raise EvidenceServiceError("Forbidden — only the author can edit a note.")
    if body_md is not None:
        note.body_md = body_md
    if pinned is not None:
        note.pinned = pinned
    await db.flush()
    await db.refresh(note)
    return note


async def delete_note(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    note_id: UUID,
    requester_id: UUID,
    requester_is_admin: bool,
) -> None:
    """Delete a note. Author or tenant admin only."""
    note = await get_note(
        db, tenant_id=tenant_id, dossier_id=dossier_id, note_id=note_id
    )
    if note is None:
        raise EvidenceServiceError("Note not found.")
    if note.author_id != requester_id and not requester_is_admin:
        raise EvidenceServiceError("Forbidden — only the author or an admin may delete.")
    await db.delete(note)
    await db.flush()


# ─── Step links ─────────────────────────────────────────────────────────────


async def create_link(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    node_id: str | None,
    url: str,
    title: str | None,
    description: str | None,
    added_by: UUID | None,
) -> DossierStepLink:
    await _ensure_dossier_exists(db, tenant_id=tenant_id, dossier_id=dossier_id)
    link = DossierStepLink(
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        node_id=node_id or None,
        url=url,
        title=title,
        description=description,
        added_by=added_by,
    )
    db.add(link)
    await db.flush()
    await db.refresh(link)
    return link


async def list_links(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    node_id: str | None = None,
) -> list[DossierStepLink]:
    await _ensure_dossier_exists(db, tenant_id=tenant_id, dossier_id=dossier_id)
    query = select(DossierStepLink).where(
        DossierStepLink.tenant_id == tenant_id,
        DossierStepLink.dossier_id == dossier_id,
    )
    if node_id is not None:
        query = query.where(DossierStepLink.node_id == node_id)
    query = query.order_by(DossierStepLink.added_at.desc())
    return list((await db.execute(query)).scalars().all())


async def get_link(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    link_id: UUID,
) -> DossierStepLink | None:
    return (
        await db.execute(
            select(DossierStepLink).where(
                DossierStepLink.tenant_id == tenant_id,
                DossierStepLink.dossier_id == dossier_id,
                DossierStepLink.id == link_id,
            )
        )
    ).scalar_one_or_none()


async def delete_link(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    link_id: UUID,
    requester_id: UUID,
    requester_is_admin: bool,
) -> None:
    """Delete a link. Adder or tenant admin only."""
    link = await get_link(
        db, tenant_id=tenant_id, dossier_id=dossier_id, link_id=link_id
    )
    if link is None:
        raise EvidenceServiceError("Link not found.")
    if link.added_by != requester_id and not requester_is_admin:
        raise EvidenceServiceError("Forbidden — only the adder or an admin may delete.")
    await db.delete(link)
    await db.flush()


# ─── Draft auto-save ────────────────────────────────────────────────────────


async def save_node_draft(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    node_id: str,
    values: dict[str, Any],
) -> datetime:
    """Persist partial form values for a paused human_input node.

    We DO NOT advance the workflow — submission is a separate endpoint.
    The values are merged into the WAITING_INPUT node_run's `input_data`
    under the `pending_draft` key (preserved across the eventual submit).

    Returns the saved_at timestamp for the SaveIndicator UI.
    """
    dossier = await _ensure_dossier_exists(
        db, tenant_id=tenant_id, dossier_id=dossier_id
    )
    if dossier.workflow_run_id is None:
        raise EvidenceServiceError("Dossier has no workflow run.")

    node_run = (
        await db.execute(
            select(PlaybookRunStep).where(
                PlaybookRunStep.run_id == dossier.workflow_run_id,
                PlaybookRunStep.node_id == node_id,
                PlaybookRunStep.status == NodeRunStatus.WAITING_INPUT,
            )
        )
    ).scalar_one_or_none()
    if node_run is None:
        raise EvidenceServiceError(
            f"No waiting_input node_run found for node {node_id!r}."
        )

    # Merge into input_data under "pending_draft" so we don't clobber the
    # form descriptor (title / fields / submit_label) the engine wrote on
    # node entry.
    input_data = dict(node_run.input_data or {})
    input_data["pending_draft"] = {
        **(input_data.get("pending_draft") or {}),
        **values,
        "_saved_at": datetime.now(tz=UTC).isoformat(),
    }
    node_run.input_data = input_data
    # Bump the dossier.updated_at so the listing surfaces "in progress".
    dossier.updated_at = datetime.now(tz=UTC)
    await db.flush()
    saved_at = datetime.fromisoformat(input_data["pending_draft"]["_saved_at"])
    return saved_at


__all__ = [
    "EvidenceServiceError",
    "create_attachment",
    "create_link",
    "create_note",
    "delete_attachment",
    "delete_link",
    "delete_note",
    "get_attachment",
    "get_link",
    "get_note",
    "list_attachments",
    "list_links",
    "list_notes",
    "open_attachment_blob",
    "save_node_draft",
    "update_note",
]
