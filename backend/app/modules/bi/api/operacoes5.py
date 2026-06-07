"""BI — endpoints da pagina /bi/operacoes5 (espinha de drill por dimensao).

Drill UA -> Produto -> Cedente -> Operacao -> Documento (Sacado na Fase 2),
aplicando o padrao de navegacao (docs/navegacao-aprofundamento.md):
- ranking de cedentes (overview)            -> GET /operacoes5/cedentes
- operacoes de um cedente (rota do cedente) -> GET /operacoes5/operacoes  (?cedente_id=)
- documentos de uma operacao (drawer)       -> GET /operacoes5/operacoes/{operacao_id}/documentos

Regime CAIXA (wh_operacao + wh_titulo). Toda agregada passa por `_apply_filters`
(§7.2) e reconcilia on-screen (§14.6).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.bi.api.deps import bi_filters
from app.modules.bi.schemas.common import BIFilters, BIResponse
from app.modules.bi.schemas.operacoes5 import (
    Operacoes5CedentesData,
    Operacoes5DocumentosData,
    Operacoes5OperacoesData,
)
from app.modules.bi.services import operacoes5 as svc

router = APIRouter(prefix="/operacoes5", tags=["bi:operacoes5"])

_Guard = Depends(require_module(Module.BI, Permission.READ))


@router.get("/cedentes", response_model=BIResponse[Operacoes5CedentesData])
async def cedentes(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[Operacoes5CedentesData]:
    """Ranking de cedentes no periodo (nivel Cedente da espinha de drill).

    Retorna TODOS os cedentes (sem corte) ordenados por VOP; reconcilia com o
    VOP total da pagina (§14.6). Aplica filtros globais via `_apply_filters`.
    """
    data, prov = await svc.get_cedentes_ranking(
        db, principal.tenant_id, filters.model_dump()
    )
    return BIResponse(data=data, provenance=prov)


@router.get("/operacoes", response_model=BIResponse[Operacoes5OperacoesData])
async def operacoes(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[Operacoes5OperacoesData]:
    """Operacoes de um cedente (`?cedente_id=`) — alimenta a rota do cedente.

    1 linha por operacao; reconcilia: sum(operacoes.vop) == vop_total. Demais
    filtros globais (periodo, UA, produto) continuam aplicados via
    `_apply_filters`.
    """
    data, prov = await svc.get_operacoes_por_cedente(
        db, principal.tenant_id, filters.model_dump()
    )
    return BIResponse(data=data, provenance=prov)


@router.get(
    "/operacoes/{operacao_id}/documentos",
    response_model=BIResponse[Operacoes5DocumentosData],
)
async def documentos(
    operacao_id: int,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _Guard,
) -> BIResponse[Operacoes5DocumentosData]:
    """Documentos (titulos) de uma operacao — conteudo inline do drawer.

    Decomposicao integral da operacao (todos os titulos, escopo de tenant);
    reconcilia com o valor da operacao (§14.6). Sem filtro de periodo: os
    titulos sao a explicacao completa da operacao.
    """
    data, prov = await svc.get_documentos_por_operacao(
        db, principal.tenant_id, operacao_id
    )
    return BIResponse(data=data, provenance=prov)
