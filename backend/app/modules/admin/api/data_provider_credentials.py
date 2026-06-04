"""CRUD of data-provider credentials (system maintainer only).

Stored in the global `provedor_dados_credencial` table — encrypted at rest via
envelope encryption (`app.shared.crypto.envelope`). The plaintext secret is
NEVER returned by GET endpoints. Mirrors `ai_provider_credentials.py`.

Nivel MANTENEDOR: credenciais de fontes externas (BigDataCorp, Infosimples...)
vivem aqui, sem `tenant_id`. O Serasa por-tenant continua em
`tenant_source_config` (decisao 2026-06-04, ver docs/esteira-credito-fontes-externas.md).
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
from app.shared.crypto.envelope import decrypt_envelope, encrypt_envelope
from app.shared.data_providers.models.credential import DataProviderCredential
from app.shared.data_providers.models.provider import DataProvider
from app.shared.data_providers.schemas import (
    DataProviderCredentialCreate,
    DataProviderCredentialRead,
    DataProviderCredentialUpdate,
    DataProviderRead,
)

router = APIRouter(prefix="/data-providers", tags=["admin:data-providers"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


def _to_read(row: DataProviderCredential) -> DataProviderCredentialRead:
    return DataProviderCredentialRead(
        id=row.id,
        provider_id=row.provider_id,
        alias=row.alias,
        zdr_enabled=row.zdr_enabled,
        active=row.active,
        rotated_at=row.rotated_at,
        notes=row.notes,
        created_at=row.created_at,
    )


@router.get("", response_model=list[DataProviderRead], dependencies=_GUARD)
async def list_providers(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DataProviderRead]:
    """Provedores cadastrados — pra o UI escolher ao criar a credencial."""
    rows = (
        await db.execute(select(DataProvider).order_by(DataProvider.name))
    ).scalars().all()
    return [DataProviderRead.model_validate(r) for r in rows]


@router.get(
    "/credentials",
    response_model=list[DataProviderCredentialRead],
    dependencies=_GUARD,
)
async def list_credentials(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DataProviderCredentialRead]:
    rows = (
        await db.execute(
            select(DataProviderCredential).order_by(
                DataProviderCredential.created_at.desc()
            )
        )
    ).scalars().all()
    return [_to_read(r) for r in rows]


@router.post(
    "/credentials",
    response_model=DataProviderCredentialRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=_GUARD,
)
async def create_credential(
    payload: DataProviderCredentialCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataProviderCredentialRead:
    if not payload.secret:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="secret nao pode ser vazio.",
        )
    provider = await db.get(DataProvider, payload.provider_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider nao encontrado.",
        )
    row = DataProviderCredential(
        provider_id=payload.provider_id,
        alias=payload.alias,
        encrypted_payload=encrypt_envelope(dict(payload.secret)),
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
    "/credentials/{credential_id}",
    response_model=DataProviderCredentialRead,
    dependencies=_GUARD,
)
async def update_credential(
    credential_id: UUID,
    payload: DataProviderCredentialUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataProviderCredentialRead:
    row = await db.get(DataProviderCredential, credential_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credencial nao encontrada."
        )

    # Re-ciphers only when a new secret is provided (merge over current).
    if payload.secret:
        current = decrypt_envelope(row.encrypted_payload)
        row.encrypted_payload = encrypt_envelope({**current, **payload.secret})
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
    "/credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_GUARD,
)
async def delete_credential(
    credential_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    row = await db.get(DataProviderCredential, credential_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credencial nao encontrada."
        )
    await db.delete(row)
    await db.commit()
