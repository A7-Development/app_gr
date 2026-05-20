"""BI — endpoints da L2 Operacoes4 (Mes Corrente · controladoria).

Endpoints da pagina `/bi/operacoes4`. Estado atual entrega apenas
`/lens-receitas` (alimenta L3 — composicao da receita + yield efetivo por
DU). Demais necessidades (cedentes enriquecido, diaria enriquecida) ganham
endpoints proprios em iteracoes seguintes (PR3 no SPEC).

Convive com os routers `operacoes2.py` (lente legada) sem sobreposicao —
todos os endpoints aqui sao prefixados por `/operacoes4`.
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
from app.modules.bi.schemas.operacoes4 import (
    Operacoes4DiariaData,
    Operacoes4LensReceitasData,
)
from app.modules.bi.services import operacoes4 as svc

router = APIRouter(prefix="/operacoes4", tags=["bi:operacoes4"])

_Guard = Depends(require_module(Module.BI, Permission.READ))


def _filter_dict(f: BIFilters) -> dict:
    return f.model_dump()


@router.get("/lens-receitas", response_model=BIResponse[Operacoes4LensReceitasData])
async def lens_receitas(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[Operacoes4LensReceitasData]:
    """Composicao da receita MTD em 4 buckets + yield efetivo por DU.

    Regime CAIXA (wh_operacao). Buckets: desagio, tarifa_cessao,
    tarifas_operacionais, outras. Comparativo: paridade DU do mes
    anterior. Yield wavg ponderado por VOP. Toda query passa por
    `_apply_filters` (§7.2).
    """
    data, prov = await svc.get_lens_receitas(
        db, principal.tenant_id, _filter_dict(filters)
    )
    return BIResponse(data=data, provenance=prov)


@router.get("/diaria", response_model=BIResponse[Operacoes4DiariaData])
async def diaria(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[Operacoes4DiariaData]:
    """Serie narrativa diaria do mes corrente (L7) — 1 linha por DU.

    Inclui VOP, receita (regime caixa, 4 buckets), yield_pct, delta vs DU
    paridade do mes anterior e flag de outlier (P5/P95 do MTD OU
    |Δ DU-par| > 50%). Aplica filtros globais via `_apply_filters` (§7.2).
    """
    data, prov = await svc.get_diaria_enriquecida(
        db, principal.tenant_id, _filter_dict(filters)
    )
    return BIResponse(data=data, provenance=prov)
