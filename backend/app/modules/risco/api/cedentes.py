"""Painel de Risco de Cedentes.

GET /risco/cedentes -> ranking com risco composto + subscores por indicador
                       + tendencia (delta vs snapshot mais antigo na janela).

O snapshot e consolidado apos cada scoring (job 6h ou "Pontuar agora") —
esta rota so LE a serie temporal.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.risco.services.cedente_risco import painel

router = APIRouter(tags=["risco:cedentes"])

_GuardRead = Depends(require_module(Module.RISCO, Permission.READ))


class IndicadorCedente(BaseModel):
    indicador: str
    subscore: float
    valor_avaliado: float
    valor_em_risco: float
    n_eventos: int | None
    n_criticos: int | None
    n_alto_risco: int | None
    componentes: dict[str, Any] | None


class CedenteRiscoRow(BaseModel):
    cedente_documento: str
    cedente_nome: str | None
    risco: float
    tendencia: float | None
    data_ref: Any
    valor_avaliado: float
    valor_em_risco: float
    n_eventos: int
    n_criticos: int
    n_alto_risco: int
    indicadores: list[IndicadorCedente]
    componentes: dict[str, Any] | None = None


@router.get("/cedentes", response_model=list[CedenteRiscoRow])
async def list_cedentes(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tendencia_dias: Annotated[int, Query(ge=7, le=365)] = 30,
    _: None = _GuardRead,
) -> list[CedenteRiscoRow]:
    rows = await painel(db, principal.tenant_id, tendencia_dias=tendencia_dias)
    return [CedenteRiscoRow(**r) for r in rows]
