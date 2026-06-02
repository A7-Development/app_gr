"""BI -> L2 Panorama (Observatorio FIDC — analise ampla do segmento CVM).

Endpoints da pagina `/bi/panorama`. Fonte: schema federado `cvm_remote.*`
(postgres_fdw, dado publico CVM FIDC). Sem escopo de tenant (CLAUDE.md 13.1).

Fase 1: GET /panorama/visao-geral (KPIs + evolucao do PL + condominio +
tamanho). Demais abas (players, risco-liquidez, lastro-prazo, concentracao)
ganham endpoints proprios em iteracoes seguintes — todos sob `/panorama`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.modules.bi.schemas.common import BIResponse
from app.modules.bi.schemas.panorama import PanoramaFilters, VisaoGeralData
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
