"""Pydantic schemas for invitation flow (Owner + public accept)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import TenantRole


class InvitationCreate(BaseModel):
    """POST /admin/users/invitations payload (Owner invites someone)."""

    email: EmailStr
    role: TenantRole = TenantRole.MEMBER


class InvitationRead(BaseModel):
    """A pending or historical invitation row (no plaintext token)."""

    id: UUID
    tenant_id: UUID
    email: EmailStr
    role: TenantRole
    invited_by_id: UUID | None
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class InvitationCreateResponse(BaseModel):
    """Response of a fresh invitation creation — includes the plaintext token.

    The token is shown ONCE (this response). Server stores only its hash.
    The maintainer/owner uses `accept_url` to forward the link to the invitee
    (email, slack, whatever the workflow is in this MVP — real SMTP later).
    """

    invitation: InvitationRead
    token: str
    accept_url: str


class InvitationContext(BaseModel):
    """GET /invitations/{token} response — non-sensitive context for the form.

    Returns just enough info to render the accept page (tenant + role +
    email) without exposing anything else about the tenant or other users.
    """

    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    email: EmailStr
    role: TenantRole
    expires_at: datetime


class InvitationAcceptRequest(BaseModel):
    """POST /invitations/{token}/accept payload."""

    name: str = Field(..., min_length=2, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
