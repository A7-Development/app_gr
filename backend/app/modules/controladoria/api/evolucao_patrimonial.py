"""Controladoria · Evolucao Patrimonial -- endpoints."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.controladoria.schemas.evolucao_patrimonial import (
    ClasseCota,
    EvolucaoPatrimonialResponse,
    Granularidade,
)
from app.modules.controladoria.services.evolucao_patrimonial import (
    compute_evolucao_patrimonial,
)

router = APIRouter(
    prefix="/evolucao-patrimonial", tags=["controladoria:evolucao-patrimonial"]
)

_Guard = Depends(require_module(Module.CONTROLADORIA, Permission.READ))


@router.get("/serie", response_model=EvolucaoPatrimonialResponse)
async def serie(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[
        UUID, Query(description="UUID da Unidade Administrativa (FIDC)")
    ],
    periodo_inicio: Annotated[
        date | None,
        Query(description="Inicio do periodo. Default: 12M corridos antes do fim."),
    ] = None,
    periodo_fim: Annotated[
        date | None,
        Query(description="Fim do periodo. Default: ultima data publicada."),
    ] = None,
    granularidade: Annotated[
        Granularidade,
        Query(description="Granularidade da serie: 'diaria' ou 'mensal'."),
    ] = "mensal",
    classes: Annotated[
        list[ClasseCota] | None,
        Query(description="Filtro de classes (sub|mez|sr). Default: todas."),
    ] = None,
    _: None = _Guard,
) -> EvolucaoPatrimonialResponse:
    """Serie temporal da evolucao do PL do passivo do FIDC (todas as classes).

    Le silver `wh_mec_evolucao_cotas` (PL, cota, quantidade, fluxo, variacoes)
    + `wh_rentabilidade_fundo` (% do CDI, rentabilidade real, retorno do CDI).
    Devolve serie por ponto (diaria ou mes-a-mes), resumo por classe e KPIs do
    fundo no periodo.

    Multi-tenant: scope enforced via `principal.tenant_id` no service.
    """
    try:
        return await compute_evolucao_patrimonial(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            granularidade=granularidade,
            classes_filtro=classes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
