"""Pydantic schemas for /credito/dossies/{id}/{attachments,notes,links} endpoints.

These shape the right-rail Evidence panel: files attached during the analysis,
markdown notes the analyst writes per step, and external URL references.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

# ─── Attachments ────────────────────────────────────────────────────────────


class AttachmentRead(BaseModel):
    """Detailed view of a dossier attachment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dossier_id: UUID
    node_id: str | None
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    description: str | None
    uploaded_by: UUID | None
    uploaded_at: datetime


class AttachmentCreateMeta(BaseModel):
    """Metadata fields submitted alongside the multipart file upload.

    The actual file blob is read from `UploadFile` in the endpoint; this
    schema is only for the JSON-encoded form fields that come with it.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str | None = Field(None, max_length=128)
    description: str | None = Field(None, max_length=2000)


# ─── Step notes ─────────────────────────────────────────────────────────────


class NoteRead(BaseModel):
    """Detailed view of a step note."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dossier_id: UUID
    node_id: str
    body_md: str
    pinned: bool
    author_id: UUID | None
    created_at: datetime
    updated_at: datetime


class NoteCreate(BaseModel):
    """Input to create a new step note."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, max_length=128)
    body_md: str = Field(..., min_length=1, max_length=10000)
    pinned: bool = False


class NoteUpdate(BaseModel):
    """Input to edit an existing step note (author-only)."""

    model_config = ConfigDict(extra="forbid")

    body_md: str | None = Field(None, min_length=1, max_length=10000)
    pinned: bool | None = None


# ─── Step links ─────────────────────────────────────────────────────────────


class LinkRead(BaseModel):
    """Detailed view of a step link."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dossier_id: UUID
    node_id: str | None
    url: str
    title: str | None
    description: str | None
    added_by: UUID | None
    added_at: datetime


class LinkCreate(BaseModel):
    """Input to create a new step link."""

    model_config = ConfigDict(extra="forbid")

    node_id: str | None = Field(None, max_length=128)
    url: HttpUrl
    title: str | None = Field(None, max_length=512)
    description: str | None = Field(None, max_length=2000)


# ─── Draft auto-save ────────────────────────────────────────────────────────


class NodeDraftPayload(BaseModel):
    """Payload for the auto-save endpoint of a paused human_input node.

    The frontend debounces field blur by 500ms and PATCHes the partial
    `values` to the backend. The engine writes them into the node_run's
    pending_input slot WITHOUT advancing the run — submission stays a
    distinct step (POST .../submit).
    """

    model_config = ConfigDict(extra="forbid")

    values: dict[str, object]


class NodeDraftResponse(BaseModel):
    """Response body of the draft auto-save."""

    saved_at: datetime
    node_id: str


__all__ = [
    "AttachmentCreateMeta",
    "AttachmentRead",
    "LinkCreate",
    "LinkRead",
    "NodeDraftPayload",
    "NodeDraftResponse",
    "NoteCreate",
    "NoteRead",
    "NoteUpdate",
]
