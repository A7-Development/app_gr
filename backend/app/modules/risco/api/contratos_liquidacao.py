"""Contrato de liquidacao por produto — primeira tela do modulo Risco.

GET  /risco/contratos-liquidacao                   -> listagem (contrato ativo
                                                      + perfil observado + divergencias)
PUT  /risco/contratos-liquidacao/{sigla}           -> define/redefine (NOVA versao)
GET  /risco/contratos-liquidacao/{sigla}/versoes   -> historico de versoes

Contracts are append-only (premise_set style); the signal engine (F4) reads
the latest version. Every (re)definition writes decision_log
(CONFIGURATION_CHANGE) inside the service.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.risco.schemas.contrato_liquidacao import (
    ContratoLiquidacaoRow,
    ContratoLiquidacaoUpdate,
    ContratoLiquidacaoVersao,
)
from app.modules.risco.services import contrato_liquidacao as svc

router = APIRouter(prefix="/contratos-liquidacao", tags=["risco:contratos-liquidacao"])

_GuardRead = Depends(require_module(Module.RISCO, Permission.READ))
_GuardWrite = Depends(require_module(Module.RISCO, Permission.WRITE))

_JanelaDias = Annotated[int, Query(ge=7, le=1830, description="Janela do perfil observado")]


@router.get("", response_model=list[ContratoLiquidacaoRow])
async def list_contratos(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    janela_dias: _JanelaDias = 180,
    _: None = _GuardRead,
) -> list[ContratoLiquidacaoRow]:
    return await svc.list_contratos(db, principal.tenant_id, janela_dias=janela_dias)


@router.put("/{produto_sigla}", response_model=ContratoLiquidacaoRow)
async def definir_contrato(
    produto_sigla: str,
    body: ContratoLiquidacaoUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    janela_dias: _JanelaDias = 180,
    _: None = _GuardWrite,
) -> ContratoLiquidacaoRow:
    novo = await svc.definir_contrato(
        db, principal.tenant_id, produto_sigla, body, user_id=principal.user_id
    )
    if novo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto nao encontrado neste tenant.",
        )
    await db.commit()
    row = await svc.get_contrato(
        db, principal.tenant_id, produto_sigla, janela_dias=janela_dias
    )
    assert row is not None  # produto validated above
    return row


@router.get("/{produto_sigla}/versoes", response_model=list[ContratoLiquidacaoVersao])
async def list_versoes(
    produto_sigla: str,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardRead,
) -> list[ContratoLiquidacaoVersao]:
    versoes = await svc.list_versoes(db, principal.tenant_id, produto_sigla)
    if not versoes:
        # Distinguish "produto sem contrato" (200 []) from sigla inexistente (404).
        existe = await svc.get_contrato(db, principal.tenant_id, produto_sigla)
        if existe is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto nao encontrado neste tenant.",
            )
    return versoes
