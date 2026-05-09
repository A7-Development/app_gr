"""CRUD of AI provider credentials (system maintainer only).

Stored in the global `ai_provider_credential` table — encrypted at rest via
envelope encryption (reuses `app.shared.crypto`). The plaintext API key is
NEVER returned by GET endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.system_maintainer_guard import require_system_maintainer
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.ai.models.provider_credential import AIProviderCredential
from app.shared.ai.schemas import (
    ProviderCredentialCreate,
    ProviderCredentialRead,
    ProviderCredentialUpdate,
)
from app.shared.crypto.envelope import decrypt_envelope, encrypt_envelope

router = APIRouter(prefix="/ai/providers", tags=["admin:ai-providers"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


def _to_read(row: AIProviderCredential) -> ProviderCredentialRead:
    return ProviderCredentialRead(
        id=row.id,
        provider=row.provider,
        alias=row.alias,
        zdr_enabled=row.zdr_enabled,
        active=row.active,
        rotated_at=row.rotated_at,
        notes=row.notes,
        created_at=row.created_at,
    )


@router.get("", response_model=list[ProviderCredentialRead], dependencies=_GUARD)
async def list_credentials(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ProviderCredentialRead]:
    rows = (
        await db.execute(
            select(AIProviderCredential).order_by(AIProviderCredential.created_at.desc())
        )
    ).scalars().all()
    return [_to_read(r) for r in rows]


@router.post(
    "",
    response_model=ProviderCredentialRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=_GUARD,
)
async def create_credential(
    payload: ProviderCredentialCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProviderCredentialRead:
    encrypted = encrypt_envelope(
        {"api_key": payload.api_key, "org_id": payload.org_id}
    )
    row = AIProviderCredential(
        provider=payload.provider,
        alias=payload.alias,
        encrypted_key=encrypted,
        zdr_enabled=payload.zdr_enabled,
        active=True,
        rotated_at=datetime.now(UTC),
        rotated_by=principal.user_id,
        notes=payload.notes,
    )
    db.add(row)
    try:
        await db.commit()
    except Exception:  # IntegrityError on duplicate alias
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alias '{payload.alias}' ja existe.",
        ) from None
    await db.refresh(row)
    return _to_read(row)


@router.put(
    "/{credential_id}",
    response_model=ProviderCredentialRead,
    dependencies=_GUARD,
)
async def update_credential(
    credential_id: UUID,
    payload: ProviderCredentialUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProviderCredentialRead:
    row = await db.get(AIProviderCredential, credential_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credencial nao encontrada."
        )

    # Re-cipher only when api_key/org_id changed; preserve other secret fields.
    if payload.api_key is not None or payload.org_id is not None:
        current = decrypt_envelope(row.encrypted_key)
        merged = {
            "api_key": payload.api_key if payload.api_key is not None else current["api_key"],
            "org_id": payload.org_id if payload.org_id is not None else current.get("org_id"),
        }
        row.encrypted_key = encrypt_envelope(merged)
        row.rotated_at = datetime.now(UTC)
        row.rotated_by = principal.user_id

    if payload.zdr_enabled is not None:
        row.zdr_enabled = payload.zdr_enabled
    if payload.active is not None:
        row.active = payload.active
    if payload.notes is not None:
        row.notes = payload.notes

    await db.commit()
    await db.refresh(row)
    return _to_read(row)


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_GUARD,
)
async def delete_credential(
    credential_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    row = await db.get(AIProviderCredential, credential_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credencial nao encontrada."
        )
    await db.delete(row)
    await db.commit()
