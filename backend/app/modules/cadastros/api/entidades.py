"""Endpoints REST: /cadastros/entidades.

Ficha da Entidade (party model). Por ora apenas o resumo consumido pelo
`<EntidadePeek />` (drawer global). A rota da ficha completa entra na
proxima fase.

`{documento}` aceita CPF/CNPJ com ou sem mascara — normalizado server-side
(mesma politica de identidade do warehouse, app/shared/documento.py).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.cadastros.schemas.entidade import EntidadeResumoOut
from app.modules.cadastros.services import entidade as svc

router = APIRouter(prefix="/entidades", tags=["cadastros:entidades"])

_GuardRead = Depends(require_module(Module.CADASTROS, Permission.READ))


@router.get(
    "/{documento}/resumo",
    response_model=EntidadeResumoOut,
    dependencies=[_GuardRead],
)
async def resumo(
    documento: str,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EntidadeResumoOut:
    data = await svc.get_resumo(db, principal.tenant_id, documento)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entidade nao encontrada para este documento.",
        )
    return EntidadeResumoOut(**data)
