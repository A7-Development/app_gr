"""Controladoria · Lamina mensal do FIDC -- endpoints.

Documento (fact sheet) de 3 paginas A4 do FIDC, alimentado 100% pelas silver
alimentadas pela QiTech. Sempre de competencia FECHADA (mes anterior ao
corrente); a parcial do mes corrente nunca e servida.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.controladoria.schemas.lamina import (
    CompetenciasResponse,
    LaminaResponse,
)
from app.modules.controladoria.services.lamina import compute_lamina, list_competencias

router = APIRouter(prefix="/lamina", tags=["controladoria:lamina"])

_Guard = Depends(require_module(Module.CONTROLADORIA, Permission.READ))


@router.get("/competencias", response_model=CompetenciasResponse)
async def competencias(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[
        UUID | None,
        Query(description="UUID da UA (FIDC). Omitido: usa o FIDC do tenant."),
    ] = None,
    _: None = _Guard,
) -> CompetenciasResponse:
    """Lista as competencias FECHADAS disponiveis (desc). Nunca o mes corrente."""
    try:
        return await list_competencias(
            db, tenant_id=principal.tenant_id, fundo_id=fundo_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("", response_model=LaminaResponse)
async def lamina(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[
        UUID | None,
        Query(description="UUID da UA (FIDC). Omitido: usa o FIDC do tenant."),
    ] = None,
    competencia: Annotated[
        str | None,
        Query(
            description="Competencia YYYY-MM. Omitida/parcial/invalida: usa a "
            "ultima competencia fechada.",
        ),
    ] = None,
    _: None = _Guard,
) -> LaminaResponse:
    """Payload completo da lamina mensal do FIDC (3 paginas).

    Le silver `wh_mec_evolucao_cotas`, `wh_rentabilidade_fundo`,
    `wh_estoque_recebivel` e `wh_saldo_conta_corrente`. Multi-tenant: escopo via
    `principal.tenant_id`. Competencia sempre fechada (regra no service).
    """
    try:
        return await compute_lamina(
            db,
            tenant_id=principal.tenant_id,
            fundo_id=fundo_id,
            competencia=competencia,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
