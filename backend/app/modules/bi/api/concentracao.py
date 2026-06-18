"""BI -> L2 Concentracao — endpoint.

`GET /bi/concentracao` — Top-10 cedentes e sacados por valor presente / PL
total do fundo (Realinvest), + serie historica diaria. CLAUDE.md §10
(escopo de tenant) + §13.2.1 (silver-only).
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.bi.schemas.common import BIResponse
from app.modules.bi.schemas.concentracao import ConcentracaoData
from app.modules.bi.services import concentracao as svc

router = APIRouter(prefix="/concentracao", tags=["bi:concentracao"])

_Guard = Depends(require_module(Module.BI, Permission.READ))


@router.get("", response_model=BIResponse[ConcentracaoData], dependencies=[_Guard])
async def concentracao(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    ua_id: Annotated[
        UUID | None,
        Query(description="UA (fundo). Vazio = Realinvest (default)."),
    ] = None,
    data: Annotated[
        date | None,
        Query(description="Data da posicao (YYYY-MM-DD). Vazio = ultima disponivel."),
    ] = None,
    janela: Annotated[
        str, Query(description="Janela do historico: 6m|12m|24m|tudo.")
    ] = "12m",
) -> BIResponse[ConcentracaoData]:
    """Concentracao da carteira FIDC: Top-10 cedentes/sacados por valor presente
    sobre o PL total do fundo + historico diario."""
    data_out, prov = await svc.get_concentracao(
        db, tenant_id=principal.tenant_id, ua_id=ua_id, data=data, janela=janela
    )
    return BIResponse(data=data_out, provenance=prov)
