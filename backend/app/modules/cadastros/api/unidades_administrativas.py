"""Endpoints REST: /cadastros/unidades-administrativas.

CRUD basico. Todos os endpoints exigem `require_module(Module.CADASTROS, ...)`
(CLAUDE.md secao 12.3). Permissoes:
    - GET (list/detalhe): READ
    - POST/PATCH/DELETE: WRITE
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.cadastros.models.unidade_administrativa import (
    TipoUnidadeAdministrativa,
)
from app.modules.cadastros.schemas.unidade_administrativa import (
    UnidadeAdministrativaCreate,
    UnidadeAdministrativaOut,
    UnidadeAdministrativaUpdate,
)
from app.modules.cadastros.services import unidade_administrativa as svc
from app.modules.cadastros.services.unidade_administrativa import UAConflictError

router = APIRouter(prefix="/unidades-administrativas", tags=["cadastros:ua"])

_GuardRead = Depends(require_module(Module.CADASTROS, Permission.READ))
_GuardWrite = Depends(require_module(Module.CADASTROS, Permission.WRITE))


@router.get("", response_model=list[UnidadeAdministrativaOut])
async def list_uas(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    ativa: bool | None = None,
    tipo: TipoUnidadeAdministrativa | None = None,
    _: None = _GuardRead,
) -> list[UnidadeAdministrativaOut]:
    """Lista UAs do tenant. Filtros opcionais: `ativa`, `tipo`."""
    rows = await svc.list_uas(
        db, tenant_id=principal.tenant_id, ativa=ativa, tipo=tipo
    )
    return [UnidadeAdministrativaOut.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=UnidadeAdministrativaOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_ua(
    payload: UnidadeAdministrativaCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> UnidadeAdministrativaOut:
    """Cria UA. 409 se nome ou CNPJ ja existirem no tenant."""
    try:
        ua = await svc.create_ua(db, tenant_id=principal.tenant_id, payload=payload)
    except UAConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return UnidadeAdministrativaOut.model_validate(ua)


@router.get("/{ua_id}", response_model=UnidadeAdministrativaOut)
async def get_ua(
    ua_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardRead,
) -> UnidadeAdministrativaOut:
    """Detalhe de uma UA. 404 se nao existir ou pertencer a outro tenant."""
    ua = await svc.get_ua(db, tenant_id=principal.tenant_id, ua_id=ua_id)
    if ua is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="UA nao encontrada"
        )
    return UnidadeAdministrativaOut.model_validate(ua)


@router.patch("/{ua_id}", response_model=UnidadeAdministrativaOut)
async def update_ua(
    ua_id: UUID,
    payload: UnidadeAdministrativaUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> UnidadeAdministrativaOut:
    """Atualizacao parcial. Campo omitido preserva valor."""
    try:
        ua = await svc.update_ua(
            db, tenant_id=principal.tenant_id, ua_id=ua_id, payload=payload
        )
    except UAConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    if ua is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="UA nao encontrada"
        )
    return UnidadeAdministrativaOut.model_validate(ua)


@router.delete("/{ua_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ua(
    ua_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> None:
    """Remove UA. 404 se nao existir. Idempotente apos a 1a chamada."""
    deleted = await svc.delete_ua(db, tenant_id=principal.tenant_id, ua_id=ua_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="UA nao encontrada"
        )
