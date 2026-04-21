"""BI — endpoints de metadados auxiliares (taxonomias).

Proposito: alimentar filtros/dropdowns do frontend com listas controladas
(UAs, eventualmente produtos, modalidades, etc.). Diferente de
`operacoes.py` que serve agregacoes numericas, aqui entregamos a
configuracao que o usuario usa para selecionar filtros.

Proveniencia: taxonomias vivem na `wh_dim_*`, ingeridas por ETL do
adapter Bitfin (ver `app.modules.integracoes.adapters.erp.bitfin.etl`).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.bi.schemas.metadata import (
    DataMinimaResponse,
    ProdutoOption,
    UAOption,
)
from app.modules.bi.services import metadata as svc

router = APIRouter(prefix="/metadata", tags=["bi:metadata"])

_Guard = Depends(require_module(Module.BI, Permission.READ))


@router.get("/uas", response_model=list[UAOption])
async def listar_uas(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _Guard,
) -> list[UAOption]:
    """Lista Unidades Administrativas ativas do tenant atual.

    Cache agressivo no frontend (React Query, staleTime ~1h): taxonomias
    mudam muito pouco (a cada sync do Bitfin, se houver mudanca la).
    """
    uas = await svc.listar_uas(db, principal.tenant_id)
    return [UAOption(id=u.ua_id, nome=u.nome, ativa=u.ativa) for u in uas]


@router.get("/produtos", response_model=list[ProdutoOption])
async def listar_produtos(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _Guard,
) -> list[ProdutoOption]:
    """Lista produtos do tenant que tem ao menos 1 operacao efetivada.

    Cache agressivo no frontend (staleTime ~1h): taxonomia muda raramente
    (so quando novo produto e cadastrado no Bitfin + ETL sincroniza).
    Ordenado alfabeticamente por nome.
    """
    produtos = await svc.listar_produtos(db, principal.tenant_id)
    return [
        ProdutoOption(
            sigla=p.sigla.strip(),
            nome=p.nome,
            tipo_de_contrato=p.tipo_de_contrato,
            produto_de_risco=p.produto_de_risco,
        )
        for p in produtos
    ]


@router.get("/data-minima", response_model=DataMinimaResponse)
async def data_minima(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _Guard,
) -> DataMinimaResponse:
    """Data da operacao efetivada mais antiga do tenant.

    Usado pelo frontend para computar o range do preset 'ALL' no seletor
    de periodo (evita hardcode de '2000-01-01' quando o tenant so tem
    2 anos de dados, por exemplo).

    Cache no frontend: staleTime ~6h (data so muda com novo ETL do Bitfin
    trazendo operacao antiga retroativa).
    """
    dt = await svc.data_minima_operacao(db, principal.tenant_id)
    return DataMinimaResponse(data_minima=dt)
