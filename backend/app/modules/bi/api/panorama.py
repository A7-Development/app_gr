"""BI -> L2 Panorama (Observatorio FIDC — analise ampla do segmento CVM).

Endpoints da pagina `/bi/panorama`. Fonte: schema federado `cvm_remote.*`
(postgres_fdw, dado publico CVM FIDC). Sem escopo de tenant (CLAUDE.md 13.1).

Abas: GET /panorama/{visao-geral, players, lastro-prazo, risco-liquidez,
fundo-comparativo}. Todos sob `/panorama`, dado publico CVM sem tenant.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.modules.bi.schemas.common import BIResponse
from app.modules.bi.schemas.panorama import (
    FundoComparativoData,
    LastroPrazoData,
    PanoramaFilters,
    PlayersData,
    RiscoLiquidezData,
    VisaoGeralData,
)
from app.modules.bi.services import panorama as svc

router = APIRouter(prefix="/panorama", tags=["bi:panorama"])

_Guard = Depends(require_module(Module.BI, Permission.READ))


def panorama_filters(
    competencia: Annotated[
        str | None, Query(description="Competencia 'YYYY-MM'. Vazio = ultima disponivel.")
    ] = None,
    condom: Annotated[
        str | None, Query(description="Tipo de condominio: 'aberto' | 'fechado'.")
    ] = None,
    faixa_pl: Annotated[
        str | None,
        Query(description="Porte: 'lt50'|'50_200'|'200_500'|'500_1000'|'gt1000'."),
    ] = None,
    tipo_carteira: Annotated[
        str | None, Query(description="'propria' | 'cotas' (fundo de cotas/feeder).")
    ] = None,
    admin_cnpj: Annotated[
        str | None, Query(description="CNPJ do administrador (cvm cnpj_admin).")
    ] = None,
) -> PanoramaFilters:
    """Filtros globais da pagina Panorama — injetados em todo endpoint."""
    return PanoramaFilters(
        competencia=competencia,
        condom=condom,
        faixa_pl=faixa_pl,
        tipo_carteira=tipo_carteira,
        admin_cnpj=admin_cnpj,
    )


@router.get("/visao-geral", response_model=BIResponse[VisaoGeralData], dependencies=[_Guard])
async def visao_geral(
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[PanoramaFilters, Depends(panorama_filters)],
) -> BIResponse[VisaoGeralData]:
    """Aba Visao Geral: KPIs macro + evolucao do PL + condominio + tamanho.

    Todo agregado passa por `_filter_where` (§7.2). Dado publico CVM, sem
    tenant (§13.1).
    """
    data, prov = await svc.get_visao_geral(db, filters)
    return BIResponse(data=data, provenance=prov)


@router.get("/players", response_model=BIResponse[PlayersData], dependencies=[_Guard])
async def players(
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[PanoramaFilters, Depends(panorama_filters)],
) -> BIResponse[PlayersData]:
    """Aba Players: ranking de administradoras (qtd, PL, medio/mediano, liquidez)."""
    data, prov = await svc.get_players(db, filters)
    return BIResponse(data=data, provenance=prov)


@router.get("/lastro-prazo", response_model=BIResponse[LastroPrazoData], dependencies=[_Guard])
async def lastro_prazo(
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[PanoramaFilters, Depends(panorama_filters)],
) -> BIResponse[LastroPrazoData]:
    """Aba Lastro & Prazo: distribuicao da carteira a vencer por faixa de prazo."""
    data, prov = await svc.get_lastro_prazo(db, filters)
    return BIResponse(data=data, provenance=prov)


@router.get("/risco-liquidez", response_model=BIResponse[RiscoLiquidezData], dependencies=[_Guard])
async def risco_liquidez(
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[PanoramaFilters, Depends(panorama_filters)],
) -> BIResponse[RiscoLiquidezData]:
    """Aba Risco & Liquidez: matriz porte x condominio + serie do indice."""
    data, prov = await svc.get_risco_liquidez(db, filters)
    return BIResponse(data=data, provenance=prov)


@router.get(
    "/fundo-comparativo", response_model=BIResponse[FundoComparativoData], dependencies=[_Guard]
)
async def fundo_comparativo(
    db: Annotated[AsyncSession, Depends(get_db)],
    cnpj: Annotated[
        str | None, Query(description="CNPJ do fundo. Vazio = REALINVEST (fundo A7 default).")
    ] = None,
) -> BIResponse[FundoComparativoData]:
    """Aba REALINVEST vs Mercado: tear-sheet do fundo posicionado vs o mercado.

    Nao usa os filtros globais — e sobre UM fundo especifico vs o universo
    inteiro (percentis calculados contra todo o mercado e contra os pares).
    """
    data, prov = await svc.get_fundo_comparativo(db, cnpj)
    return BIResponse(data=data, provenance=prov)
