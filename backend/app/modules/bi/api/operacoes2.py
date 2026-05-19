"""BI — endpoints da L2 Operacoes2 (refatoracao 2026-05-03).

4 endpoints novos sob `/bi/operacoes2/*`:

- GET `/kpi-strip`              — 5 indicadores-chave + sparklines 12M
- GET `/aba1-mes-corrente`      — variance decomposition do mes corrente
- GET `/aba1-volume-ritmo`      — bundle completo da Aba 'Volume & Ritmo'
- GET `/aba2-produtos-pricing`  — bundle completo da Aba 'Produtos & Pricing'

Convivem com o router legado `operacoes.py` (rota `/bi/operacoes/*`) — a
nova UX vive em rota separada para nao quebrar a pagina existente.
"""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.bi.api.deps import bi_filters
from app.modules.bi.schemas.common import BIFilters, BIResponse
from app.modules.bi.schemas.operacoes2 import (
    AbaMesCorrenteData,
    AbaMesCorrenteV3Data,
    AbaProdutosPricingData,
    AbaVolumeRitmoData,
    CedentesMtdData,
    OperacoesDoDiaData,
    OperacoesKpiStripData,
    VopPotencialData,
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


@router.get(
    "/aba2-produtos-pricing", response_model=BIResponse[AbaProdutosPricingData]
)
async def aba2_produtos_pricing(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[AbaProdutosPricingData]:
    """Aba 2 — Produtos & Pricing.

    Mix temporal 12M fechados (M-12 a M-1) por produto, ranking de produtos
    com taxa/prazo/spread ponderados + MTD same-period, scatter agregado
    Taxa x Prazo, e histogramas (taxas com bucket dinamico, prazos com
    buckets fixos). TODA query passa por `_apply_filters` (regra dura sec 7.2).
    """
    data, prov = await svc.get_aba2_produtos_pricing(
        db, principal.tenant_id, _filter_dict(filters)
    )
    return BIResponse(data=data, provenance=prov)


@router.get("/vop-potencial", response_model=BIResponse[VopPotencialData])
async def vop_potencial(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[VopPotencialData]:
    """VOP Potencial -- consolidado e por UA do mes corrente.

    `vop_potencial = vop_realizado_mtd + caixa_disponivel + liquidacoes_previstas`

    - vop_realizado_mtd: SUM(Operacao.total_bruto) entre dia 1 do mes e hoje.
    - caixa_disponivel: ultima snapshot de saldo livre por (UA, conta) -- exclui
      escrow / caucao / travada (flags estruturais via wh_caixa_snapshot).
    - liquidacoes_previstas: SUM(Titulo.saldo_devedor) com situacao=0,
      saldo>0, NOT sustado, vencimento entre hoje e fim do mes.

    Default: filtra UAs com `tipo IN (1, 2)` (FIDC + Securitizadora). Quando
    `ua_id` setado nos filtros, respeita a selecao explicita do usuario.
    """
    data, prov = await svc.get_vop_potencial(
        db, principal.tenant_id, _filter_dict(filters)
    )
    return BIResponse(data=data, provenance=prov)


@router.get("/aba1-mes-corrente", response_model=BIResponse[AbaMesCorrenteData])
async def aba1_mes_corrente(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    dimension: Annotated[
        Literal["produto", "ua", "faixa_ticket"],
        Query(description="Dimensao para decomposicao das bridges (VOP/Receita/Taxa/Prazo)"),
    ] = "produto",
    _: None = _Guard,
) -> BIResponse[AbaMesCorrenteData]:
    """Aba 0 — Mes corrente (variance decomposition).

    Decompoe o delta MTD vs DU equivalente do mes anterior em 6 KPIs:
    VOP/Receita (variance bridge aditiva + projecao), Taxa/Prazo (PVM
    bridge), Mix produtos (dumbbell) e Concentracao (HHI + movements).

    `dimension` aplica-se a VOP, Receita, Taxa, Prazo. Mix e Concentracao
    sempre usam produto. TODA query passa por `_apply_filters` (regra dura
    sec 7.2). Quando `wh_dim_dia_util` esta vazia, projecoes retornam null
    (degraded mode).
    """
    data, prov = await svc.get_aba1_mes_corrente(
        db, principal.tenant_id, _filter_dict(filters), dimension
    )
    return BIResponse(data=data, provenance=prov)


@router.get("/aba3-mes-corrente", response_model=BIResponse[AbaMesCorrenteV3Data])
async def aba3_mes_corrente(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    dimension: Annotated[
        Literal["produto", "ua", "faixa_ticket"],
        Query(description="Dimensao da decomposicao do VOP Waterfall no hero L2"),
    ] = "produto",
    _: None = _Guard,
) -> BIResponse[AbaMesCorrenteV3Data]:
    """Aba '/bi/operacoes3' — Mes Corrente v3 (socio-diretor view).

    Bundle reorientado para responder "como ta o mes, onde estou ganhando/
    perdendo?" em uma piscadela:

    - **Termometro**: 5 KPIs (VOP, Receita, Taxa, Prazo, Potencial) com dupla
      comparacao (VOP-DU paridade DU + MOM normalizado por DU). Potencial
      e absoluto (sem delta).
    - **VOP do mes (hero)**: serie diaria do mes (consolidada + quebra por
      UA pra modo stacked) + variance bridge canonico decomposto por
      `dimension` (produto/ua/faixa_ticket).
    - **Decomposicao avancada**: receita/taxa/prazo/mix/concentracao
      reusados da v1 (frontend renderiza collapsible fechada por default).
    """
    data, prov = await svc.get_aba3_mes_corrente(
        db, principal.tenant_id, _filter_dict(filters), dimension
    )
    return BIResponse(data=data, provenance=prov)


@router.get("/operacoes-do-dia", response_model=BIResponse[OperacoesDoDiaData])
async def operacoes_do_dia(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    data: Annotated[
        date,
        Query(description="Dia ISO YYYY-MM-DD — clique numa barra do VOP Diario"),
    ],
    _: None = _Guard,
) -> BIResponse[OperacoesDoDiaData]:
    """Drill 'operacoes do dia X' — conteudo do DrillDownSheet.

    Lista operacoes efetivadas em `data`, KPIs agregados do dia e quebra
    por produto/UA. Aplica todos os filtros globais (`_apply_filters` §7.2)
    + tenant scope.
    """
    bundle, prov = await svc.get_operacoes_do_dia(
        db, principal.tenant_id, _filter_dict(filters), data
    )
    return BIResponse(data=bundle, provenance=prov)


@router.get("/cedentes-mtd", response_model=BIResponse[CedentesMtdData])
async def cedentes_mtd(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[BIFilters, Depends(bi_filters)],
    _: None = _Guard,
) -> BIResponse[CedentesMtdData]:
    """Tabela narrativa de cedentes MTD — alimenta L3 de /bi/operacoes3.

    Cada linha = 1 cedente com:
      - volume_mtd, delta_vs_mes_ant_pct (same-DU)
      - status: novo | recorrente | sumido
      - n_op, dias_mtd, taxa_media (ponderada)
      - primeira_op + ultima_op (historicas)

    Sumidos = cedentes do mes anterior MTD ausentes do MTD corrente
    (volume_mtd=None, delta=-100%). Aplica filtros globais (`_apply_filters`).
    """
    bundle, prov = await svc.get_cedentes_mtd(
        db, principal.tenant_id, _filter_dict(filters)
    )
    return BIResponse(data=bundle, provenance=prov)
