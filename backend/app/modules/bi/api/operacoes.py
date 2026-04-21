"""BI — endpoints da L2 Operacoes.

Todos os endpoints:
  - exigem `require_module(Module.BI, Permission.READ)` (CLAUDE.md 12.3)
  - usam o `BIFilters` compartilhado via dependency `bi_filters`
  - retornam `BIResponse[<Data>]` (payload + proveniencia)
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
from app.modules.bi.schemas.operacoes import (
    OperacoesResumo,
    SeriesEDiaUtil,
    SeriesEPrazo,
    SeriesEReceita,
    SeriesETaxa,
    SeriesETicket,
    SeriesEVolume,
)
from app.modules.bi.services import operacoes as svc

router = APIRouter(prefix="/operacoes", tags=["bi:operacoes"])

# Dependency composta: autoriza o modulo BI em leitura.
_Guard = Depends(require_module(Module.BI, Permission.READ))


def _filter_dict(f: BIFilters) -> dict:
    return f.model_dump()


@router.get("/resumo", response_model=BIResponse[OperacoesResumo])
async def resumo(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[OperacoesResumo]:
    """KPIs principais da L2 Operacoes (topo da pagina)."""
    data, prov = await svc.get_resumo(db, principal.tenant_id, _filter_dict(filters))
    return BIResponse(data=data, provenance=prov)


@router.get("/volume", response_model=BIResponse[SeriesEVolume])
async def volume(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[SeriesEVolume]:
    """L3 Volume — evolucao + cortes."""
    data, prov = await svc.get_volume(db, principal.tenant_id, _filter_dict(filters))
    return BIResponse(data=data, provenance=prov)


@router.get("/taxa", response_model=BIResponse[SeriesETaxa])
async def taxa(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[SeriesETaxa]:
    """L3 Taxa — taxa de juros media ponderada por volume."""
    data, prov = await svc.get_taxa(db, principal.tenant_id, _filter_dict(filters))
    return BIResponse(data=data, provenance=prov)


@router.get("/prazo", response_model=BIResponse[SeriesEPrazo])
async def prazo(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[SeriesEPrazo]:
    """L3 Prazo — prazo medio real ponderado por volume."""
    data, prov = await svc.get_prazo(db, principal.tenant_id, _filter_dict(filters))
    return BIResponse(data=data, provenance=prov)


@router.get("/ticket", response_model=BIResponse[SeriesETicket])
async def ticket(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[SeriesETicket]:
    """L3 Ticket — volume bruto / numero de operacoes."""
    data, prov = await svc.get_ticket(db, principal.tenant_id, _filter_dict(filters))
    return BIResponse(data=data, provenance=prov)


@router.get("/receita", response_model=BIResponse[SeriesEReceita])
async def receita(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[SeriesEReceita]:
    """L3 Receita contratada — juros + tarifas no ato da operacao."""
    data, prov = await svc.get_receita(db, principal.tenant_id, _filter_dict(filters))
    return BIResponse(data=data, provenance=prov)


@router.get("/dia-util", response_model=BIResponse[SeriesEDiaUtil])
async def dia_util(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[SeriesEDiaUtil]:
    """L3 Dia util — distribuicao de efetivacao por dia."""
    data, prov = await svc.get_dia_util(db, principal.tenant_id, _filter_dict(filters))
    return BIResponse(data=data, provenance=prov)
