"""Load and decrypt the Anthropic API credential from the global table.

The system maintainer cadastra credentials via the admin endpoint; this module
exposes a single helper that returns the active credential for use by the
adapter.

Multiple credentials per provider are allowed (e.g. one prod, one EU, one
ZDR-contracted). Picking strategy for now: most recently rotated active row.
Phase 2 will add tag-based selection (e.g. require_zdr=True at runtime).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AIProvider
from app.shared.ai.models.provider_credential import AIProviderCredential
from app.shared.crypto.envelope import decrypt_envelope


class CredentialNotFoundError(LookupError):
    """No active credential for the requested provider."""


@dataclass(slots=True)
class AnthropicCredential:
    """Decrypted credential, ready to use as HTTP headers."""

    id: UUID
    api_key: str
    org_id: str | None
    zdr_enabled: bool
    rotated_at: datetime | None


async def get_active_anthropic_credential(
    db: AsyncSession, *, require_zdr: bool = False
) -> AnthropicCredential:
    """Return the active Anthropic API credential, decrypted.

    Raises CredentialNotFoundError if no row matches.
    """
    stmt = select(AIProviderCredential).where(
        AIProviderCredential.provider == AIProvider.ANTHROPIC,
        AIProviderCredential.active.is_(True),
    )
    if require_zdr:
        stmt = stmt.where(AIProviderCredential.zdr_enabled.is_(True))
    stmt = stmt.order_by(AIProviderCredential.rotated_at.desc().nulls_last())

    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        raise CredentialNotFoundError(
            "Nenhuma credencial Anthropic ativa cadastrada. "
            "Cadastre via /admin/ia/providers."
        )

    plaintext = decrypt_envelope(row.encrypted_key)
    return AnthropicCredential(
        id=row.id,
        api_key=plaintext["api_key"],
        org_id=plaintext.get("org_id"),
        zdr_enabled=row.zdr_enabled,
        rotated_at=row.rotated_at,
    )
