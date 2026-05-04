"""BI — endpoints da L2 Operacoes2 (refatoracao 2026-05-03).

2 endpoints novos sob `/bi/operacoes2/*`:

- GET `/kpi-strip`            — 5 indicadores-chave + sparklines 12M
- GET `/aba1-volume-ritmo`    — bundle completo da Aba 1

Convivem com o router legado `operacoes.py` (rota `/bi/operacoes/*`) — a
nova UX vive em rota separada para nao quebrar a pagina existente.
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
from app.modules.bi.schemas.operacoes2 import (
    AbaVolumeRitmoData,
    OperacoesKpiStripData,
)
from app.modules.bi.services import operacoes2 as svc

router = APIRouter(prefix="/operacoes2", tags=["bi:operacoes2"])

_Guard = Depends(require_module(Module.BI, Permission.READ))


def _filter_dict(f: BIFilters) -> dict:
    return f.model_dump()


@router.get("/kpi-strip", response_model=BIResponse[OperacoesKpiStripData])
async def kpi_strip(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[OperacoesKpiStripData]:
    """KPI Strip — 5 indicadores-chave (VOP, Taxa, Prazo, Produto Top, Receita)."""
    data, prov = await svc.get_kpi_strip(
        db, principal.tenant_id, _filter_dict(filters)
    )
    return BIResponse(data=data, provenance=prov)


@router.get("/aba1-volume-ritmo", response_model=BIResponse[AbaVolumeRitmoData])
async def aba1_volume_ritmo(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[AbaVolumeRitmoData]:
    """Aba 1 — Volume & Ritmo (evolucao 12M + ritmo do mes + quebras + sazonalidade).

    Quando `wh_dim_dia_util` esta vazia, `ritmo` / `pace_diario` retornam
    `null` (degraded mode).
    """
    data, prov = await svc.get_aba1_volume_ritmo(
        db, principal.tenant_id, _filter_dict(filters)
    )
    return BIResponse(data=data, provenance=prov)
