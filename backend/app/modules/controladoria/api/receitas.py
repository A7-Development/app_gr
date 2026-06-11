"""API Receitas — 3 metodos de apuracao sobre o catalogo de receitas.

GET /controladoria/receitas/resumo        kpis + serie mensal + composicao + ponte
GET /controladoria/receitas/detalhe       familia x stream x natureza (DataTable)
GET /controladoria/receitas/cedentes      por cedente
GET /controladoria/receitas/titulos       drill de um (familia, stream)
GET /controladoria/receitas/conferencias  desconto de mora concedido

Todos com require_module(CONTROLADORIA, READ) + escopo §7.2 no service.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.controladoria.schemas.receitas import (
    Metodo,
    ReceitasCedentesResponse,
    ReceitasConferenciasResponse,
    ReceitasDetalheResponse,
    ReceitasResumoResponse,
    ReceitasTitulosResponse,
)
from app.modules.controladoria.services.receitas import (
    compute_cedentes,
    compute_conferencias,
    compute_detalhe,
    compute_resumo,
    compute_titulos,
)

router = APIRouter(prefix="/receitas", tags=["controladoria"])

_Guard = Depends(require_module(Module.CONTROLADORIA, Permission.READ))

_QDe = Annotated[date, Query(description="Primeira competencia (1o dia do mes)")]
_QAte = Annotated[date, Query(description="Ultima competencia (1o dia do mes)")]
_QMetodo = Annotated[Metodo, Query(description="caixa | competencia | acruo")]
_QFundo = Annotated[int | None, Query(description="UnidadeAdministrativa.Id Bitfin")]


def _valida_janela(de: date, ate: date) -> None:
    if ate < de:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="competencia_ate deve ser maior ou igual a competencia_de",
        )


@router.get("/resumo", response_model=ReceitasResumoResponse)
async def resumo(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    competencia_de: _QDe,
    competencia_ate: _QAte,
    metodo: _QMetodo = "caixa",
    fundo_id: _QFundo = None,
    _: None = _Guard,
) -> ReceitasResumoResponse:
    _valida_janela(competencia_de, competencia_ate)
    return await compute_resumo(
        db, tenant_id=principal.tenant_id, metodo=metodo,
        competencia_de=competencia_de, competencia_ate=competencia_ate,
        fundo_id=fundo_id,
    )


@router.get("/detalhe", response_model=ReceitasDetalheResponse)
async def detalhe(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    competencia_de: _QDe,
    competencia_ate: _QAte,
    metodo: _QMetodo = "caixa",
    fundo_id: _QFundo = None,
    _: None = _Guard,
) -> ReceitasDetalheResponse:
    _valida_janela(competencia_de, competencia_ate)
    return await compute_detalhe(
        db, tenant_id=principal.tenant_id, metodo=metodo,
        competencia_de=competencia_de, competencia_ate=competencia_ate,
        fundo_id=fundo_id,
    )


@router.get("/cedentes", response_model=ReceitasCedentesResponse)
async def cedentes(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    competencia_de: _QDe,
    competencia_ate: _QAte,
    metodo: _QMetodo = "caixa",
    fundo_id: _QFundo = None,
    _: None = _Guard,
) -> ReceitasCedentesResponse:
    _valida_janela(competencia_de, competencia_ate)
    return await compute_cedentes(
        db, tenant_id=principal.tenant_id, metodo=metodo,
        competencia_de=competencia_de, competencia_ate=competencia_ate,
        fundo_id=fundo_id,
    )


@router.get("/titulos", response_model=ReceitasTitulosResponse)
async def titulos(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    competencia_de: _QDe,
    competencia_ate: _QAte,
    familia: Annotated[str, Query()],
    stream: Annotated[str, Query()],
    metodo: _QMetodo = "caixa",
    fundo_id: _QFundo = None,
    _: None = _Guard,
) -> ReceitasTitulosResponse:
    _valida_janela(competencia_de, competencia_ate)
    return await compute_titulos(
        db, tenant_id=principal.tenant_id, metodo=metodo, familia=familia,
        stream=stream, competencia_de=competencia_de,
        competencia_ate=competencia_ate, fundo_id=fundo_id,
    )


@router.get("/conferencias", response_model=ReceitasConferenciasResponse)
async def conferencias(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    competencia_de: _QDe,
    competencia_ate: _QAte,
    fundo_id: _QFundo = None,
    _: None = _Guard,
) -> ReceitasConferenciasResponse:
    _valida_janela(competencia_de, competencia_ate)
    return await compute_conferencias(
        db, tenant_id=principal.tenant_id,
        competencia_de=competencia_de, competencia_ate=competencia_ate,
        fundo_id=fundo_id,
    )
