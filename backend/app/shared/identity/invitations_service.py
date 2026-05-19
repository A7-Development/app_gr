"""Invitation flow: generate, validate, accept.

Plaintext invitation tokens are returned only at creation time. The DB stores
a bcrypt hash so a leak of `user_invitation` does not allow accepting any
pending invite. Tokens expire after `_DEFAULT_TTL_DAYS`.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TenantRole
from app.core.security import hash_password, verify_password
from app.shared.identity.invitation import UserInvitation

# 7 days is the SaaS default (Linear, Notion, Slack, etc).
_DEFAULT_TTL_DAYS = 7

# Token shape: 32 bytes of entropy -> 43 url-safe chars.
_TOKEN_BYTES = 32


class InvitationError(Exception):
    """Base class for invitation flow errors."""


class InvitationNotFound(InvitationError):  # noqa: N818
    """Token does not match any open invitation."""


class InvitationExpired(InvitationError):  # noqa: N818
    """Invitation expired before acceptance."""


class InvitationAlreadyConsumed(InvitationError):  # noqa: N818
    """Invitation was already accepted or revoked."""


def _generate_token() -> str:
    """Return a fresh URL-safe random token (~43 chars)."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(plain: str) -> str:
    """Hash an invitation token. Same primitive as `hash_password`."""
    return hash_password(plain)


def verify_token(plain: str, hashed: str) -> bool:
    """Check a plaintext token against its stored bcrypt hash."""
    return verify_password(plain, hashed)


async def create_invitation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    email: str,
    role: TenantRole,
    invited_by_id: UUID | None,
    ttl_days: int = _DEFAULT_TTL_DAYS,
) -> tuple[UserInvitation, str]:
    """Create a fresh invitation row and return (row, plaintext_token).

    Caller is responsible for emailing the token to the invitee. If an open
    invitation already exists for (tenant, email), it is revoked first so
    only the newest one is valid (frees the partial unique index).
    """
    # Revoke any existing open invitation for the same (tenant, email) so the
    # partial unique index does not collide with the insert below.
    await db.execute(
        update(UserInvitation)
        .where(
            UserInvitation.tenant_id == tenant_id,
            UserInvitation.email == email,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )

    plaintext = _generate_token()
    row = UserInvitation(
        tenant_id=tenant_id,
        email=email,
        role=role,
        token_hash=hash_token(plaintext),
        invited_by_id=invited_by_id,
        expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
    )
    db.add(row)
    await db.flush()
    return row, plaintext


async def find_open_by_token(
    db: AsyncSession, token: str
) -> UserInvitation:
    """Resolve an open invitation by its plaintext token.

    Raises:
        InvitationNotFound: no row with a matching hash.
        InvitationExpired: matched but past expiration.
        InvitationAlreadyConsumed: matched but already accepted or revoked.

    Implementation note: bcrypt prevents bulk indexing, so we iterate over
    open invitations and verify each hash. Volume is small (handful of
    pending invites per tenant). If this becomes a hotspot, switch to
    HMAC-SHA256 with a per-row salt + index on the salted hash.
    """
    rows = (
        await db.execute(
            select(UserInvitation).where(
                UserInvitation.accepted_at.is_(None),
                UserInvitation.revoked_at.is_(None),
            )
        )
    ).scalars().all()

    for row in rows:
        if verify_token(token, row.token_hash):
            now = datetime.now(UTC)
            if row.expires_at <= now:
                raise InvitationExpired("Invitation has expired.")
            return row

    # No match — distinguish "never existed" vs "already consumed" by also
    # checking the closed rows (best-effort; not a hard guarantee since the
    # plaintext-to-row mapping is lossy by design).
    closed_rows = (
        await db.execute(
            select(UserInvitation).where(
                (UserInvitation.accepted_at.is_not(None))
                | (UserInvitation.revoked_at.is_not(None))
            )
        )
    ).scalars().all()
    for row in closed_rows:
        if verify_token(token, row.token_hash):
            raise InvitationAlreadyConsumed(
                "Invitation has already been accepted or revoked."
            )

    raise InvitationNotFound("Invitation token does not match any record.")


async def mark_accepted(db: AsyncSession, invitation: UserInvitation) -> None:
    """Mark an invitation as accepted (idempotent, in-row update)."""
    invitation.accepted_at = datetime.now(UTC)
    await db.flush()


async def revoke(db: AsyncSession, invitation: UserInvitation) -> None:
    """Mark an invitation as revoked."""
    invitation.revoked_at = datetime.now(UTC)
    await db.flush()
