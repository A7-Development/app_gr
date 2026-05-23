"""Controladoria · Cota Sub — endpoints."""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.controladoria.schemas.balancete_diario import (
    BalanceteResponseSchema,
    CosifRowsResponseSchema,
)
from app.modules.controladoria.schemas.cota_sub import (
    BalancoPatrimonialResponse,
    BalancoResponse,
    ExplicacaoVariacaoResponse,
    VariacaoDiariaResponse,
    VariacoesDiaResponse,
)
from app.modules.controladoria.schemas.cota_sub_drill import (
    DrillCprResponse,
    DrillDcResponse,
    DrillPddResponse,
)
from app.modules.controladoria.services.balancete_diario import (
    compute_balancete_diario,
    compute_cosif_rows,
)
from app.modules.controladoria.services.balanco import compute_balanco
from app.modules.controladoria.services.balanco_patrimonial import (
    compute_balanco_patrimonial,
)
from app.modules.controladoria.services.cota_sub import compute_variacao_diaria
from app.modules.controladoria.services.cota_sub_drill_cpr import compute_drill_cpr
from app.modules.controladoria.services.cota_sub_drill_dc import compute_drill_dc
from app.modules.controladoria.services.cota_sub_drill_pdd import compute_drill_pdd
from app.modules.controladoria.services.cota_sub_explainers import (
    compute_explicacao_variacao,
)
from app.modules.controladoria.services.variacoes_dia import compute_variacoes_dia
from app.modules.integracoes.public import listar_datas_disponiveis_qitech

router = APIRouter(prefix="/cota-sub", tags=["controladoria:cota-sub"])

_Guard = Depends(require_module(Module.CONTROLADORIA, Permission.READ))


@router.get("/variacao-diaria", response_model=VariacaoDiariaResponse)
async def variacao_diaria(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e calculado como dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1 (ex.: ignorar feriados nao mapeados)."),
    ] = None,
    _: None = _Guard,
) -> VariacaoDiariaResponse:
    """Decomposicao da variacao do PL Sub Jr entre D-1 e D0.

    Espelho da planilha `VariacaoDeCota_Preenchida.xlsx` (aba Analise) —
    devolve PL por categoria + decomposicao + apropriacao DC + CPR detalhado +
    sanity check (divergencia entre Σ decomposicao e Δ PL).
    """
    try:
        return await compute_variacao_diaria(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/balanco", response_model=BalancoResponse)
async def balanco(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e calculado como dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    _: None = _Guard,
) -> BalancoResponse:
    """Balanco patrimonial diario na otica do cotista subordinado.

    Devolve as 11 linhas principais + section/subtotal/total — todas
    construidas APENAS de silver canonico (CLAUDE.md §13.2.1).
    """
    try:
        return await compute_balanco(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/balanco-patrimonial", response_model=BalancoPatrimonialResponse)
async def balanco_patrimonial(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e calculado como dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1 (ex.: ignorar feriados nao mapeados)."),
    ] = None,
    _: None = _Guard,
) -> BalancoPatrimonialResponse:
    """Balanco patrimonial otica Sub Jr — fonte do Balance hero do redesign.

    Apresenta Ativos / Passivos separados (sinais absolutos), PL deduzido
    (Σ Ativos - Σ Passivos), PL na fonte (wh_mec classe Sub) e o residuo
    de identidade contabil. Quando residuo != 0, sinaliza desalinhamento
    entre o calculo do gestor e o publicado pela QiTech (snapshot parcial,
    mutacao silenciosa, etc.).
    """
    try:
        return await compute_balanco_patrimonial(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/datas-disponiveis", response_model=list[date])
async def datas_disponiveis(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    _: None = _Guard,
) -> list[date]:
    """Lista as datas em que a QiTech publicou snapshot da UA.

    Consumido pelo Calendar do frontend para impedir o usuario de selecionar
    dias sem dados (fim de semana, feriado, falha de ETL — qualquer buraco e
    tratado de forma uniforme). Le da `wh_dia_util_qitech` (silver), populada
    pelo `etl.sync_all` ao termino de cada sync (Fase B, desde
    qitech_adapter_v0.2.0).

    Multi-tenant: scope enforced via `principal.tenant_id` no service.
    """
    return await listar_datas_disponiveis_qitech(
        db,
        tenant_id=principal.tenant_id,
        ua_id=fundo_id,
    )


@router.get("/variacoes-dia", response_model=VariacoesDiaResponse)
async def variacoes_dia(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e calculado como dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    _: None = _Guard,
) -> VariacoesDiaResponse:
    """Decomposicao do Δ do PL Sub Jr entre D-1 e D0 em 3 fluxos:

      1. Apropriacoes (provisoes diarias do CPR)
      2. Pagamentos efetivados (saidas em wh_movimento_caixa)
      3. Anomalias (pagamentos sem provisao previa)

    Inclui conferencia: ΔPassivo Contabil deve casar com Σ apropriacoes.
    """
    try:
        return await compute_variacoes_dia(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/balancete-diario", response_model=BalanceteResponseSchema)
async def balancete_diario(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e calculado como dia util anterior QiTech.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    _: None = _Guard,
) -> BalanceteResponseSchema:
    """Balancete patrimonial diario COSIF + reconciliacao da Cota Subordinada.

    Modelo agnostico multi-tenant (CLAUDE.md §10). Classifica cada saldo do
    silver em conta COSIF via cascata override -> regra -> pendente
    (CosifResolution). Calcula:

      PL Cota Sub = Σ_silver_TOTAL - |Cotas Sr emitidas| - |Cotas Mez emitidas|

    Resposta inclui:

      - `nodes`: arvore COSIF hierarquica D-1 vs D0 com Δ por conta
      - `classe_breakdown_por_cosif`: quebra por classe Sr/Mez/Sub dentro
        de contas que carregam classe (ex.: 6.1.1.70.30.001)
      - `reconciliacao`: equacao da Cota Sub + residuo (deve ser ~0)
      - `cobertura`: % rows classificadas por source — KPI da UI mostra
        amber/red quando pendente > limite

    Validado contra REALINVEST 08/05/2026: residuo = 0,00, cobertura 100%.

    Multi-tenant: scope enforced via `principal.tenant_id`. Tenant A nao
    enxerga fundos de outro tenant.
    """
    try:
        result = await compute_balancete_diario(
            db,
            tenant_id=principal.tenant_id,
            fundo_id=fundo_id,
            data_d_zero=data,
            data_d_minus_1=data_anterior,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return BalanceteResponseSchema.model_validate(result.to_dict())


@router.get(
    "/balancete-diario/cosif/{cosif_codigo}/rows",
    response_model=CosifRowsResponseSchema,
)
async def balancete_diario_cosif_rows(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cosif_codigo: str,
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Data da posicao (D0).")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1. Default: dia util anterior."),
    ] = None,
    _: None = _Guard,
) -> CosifRowsResponseSchema:
    """Compara papeis de uma conta COSIF entre D-1 e D0.

    Drill-down do `CosifDrillSheet`. Mescla composicao (foto D0) com
    analise da variacao (D-1 -> D0): cada papel volta com valor_d_minus_1,
    valor_d_zero, delta e status (novo|removido|alterado|inalterado).

    Aceita conta analitica (folha) ou sintetica (agrega descendentes). Se
    `data_anterior` nao for passado, infere D-1 via `dia_util_anterior_qitech`.

    Multi-tenant: scope enforced via `principal.tenant_id` no service.
    """
    try:
        result = await compute_cosif_rows(
            db,
            tenant_id=principal.tenant_id,
            fundo_id=fundo_id,
            data_d_zero=data,
            cosif_codigo=cosif_codigo,
            data_d_minus_1=data_anterior,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return CosifRowsResponseSchema.model_validate(result.to_dict())


@router.get("/drill/dc", response_model=DrillDcResponse)
async def drill_dc(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e calculado como dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    _: None = _Guard,
) -> DrillDcResponse:
    """Drill da categoria DC (Direitos Creditorios) do Balance hero.

    Decompoe o delta da linha DC em:
      1. Aquisicoes do dia (wh_aquisicao_recebivel D0)
      2. Liquidacoes por tipo_movimento (wh_liquidacao_recebivel D0)
      3. Apropriacao derivada — formula:
           Apropriacao = ΔEstoque + Liquidacoes - Aquisicoes
    """
    try:
        return await compute_drill_dc(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/drill/pdd", response_model=DrillPddResponse)
async def drill_pdd(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e calculado como dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    threshold_brl: Annotated[
        Decimal,
        Query(description="Threshold |Δ valor_pdd| pra entrar no top papeis. Default R$ 100."),
    ] = Decimal("100"),
    top_n: Annotated[
        int,
        Query(ge=1, le=200, description="Cap de papeis no top. Default 20."),
    ] = 20,
    _: None = _Guard,
) -> DrillPddResponse:
    """Drill da categoria PDD (Provisao para Devedores Duvidosos) do Balance hero.

    Decompoe o delta da linha PDD em:
      1. PDD consolidado D-1 / D0 / Δ (fonte do balanco)
      2. PDD granular D-1 / D0 (Σ wh_estoque_recebivel.valor_pdd)
      3. Matriz de migracao de faixa A/B/C/D/E/F/G/H ↔ WOP/NOVO
      4. Papeis em write-off (WOP — saiu do estoque sem liquidacao registrada)
      5. Top N papeis por |Δ valor_pdd|
    """
    try:
        return await compute_drill_pdd(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
            threshold_brl=threshold_brl,
            top_n=top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/drill/cpr", response_model=DrillCprResponse)
async def drill_cpr(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e calculado como dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    _: None = _Guard,
) -> DrillCprResponse:
    """Drill da categoria CPR (Contas a Pagar e Receber) do Balance hero.

    Decompoe o delta da linha CPR em:
      1. Totais D-1 / D0 / Δ
      2. Agrupamento por natureza (diferimento, taxas, despesas, IOF/IR,
         aporte/devolucao, outros)
      3. Aportes engaiolados detectados (caso pedagogico REALINVEST 07-13/05)
    """
    try:
        return await compute_drill_cpr(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/explicacao", response_model=ExplicacaoVariacaoResponse)
async def explicacao_variacao(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e calculado como dia util anterior QiTech.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    threshold_brl: Annotated[
        Decimal,
        Query(description="Threshold de evidencia (|Δ| em R$). Default 100."),
    ] = Decimal("100"),
    top_n: Annotated[
        int,
        Query(ge=1, le=200, description="Cap de evidencias mostradas por categoria. Default 20."),
    ] = 20,
    _: None = _Guard,
) -> ExplicacaoVariacaoResponse:
    """Explainers heuristicos da variacao do PL Sub entre D-1 e D0.

    Por ora implementa apenas **PDD (categoria 3.2)** — cruza
    `wh_estoque_recebivel` D-1 vs D0 por papel, ordenado por `|Δ valor_pdd|`
    DESC. Demais categorias (MTM, Aporte, Movimento de cotas Sr/Mez,
    Diferimento, Liquidacao, Aquisicao) entrarao em PRs incrementais.

    Resposta lista as categorias materializadas em `explanations`; categorias
    sem variacao relevante (toda evidencia abaixo do threshold) sao omitidas.

    Multi-tenant: scope enforced via `principal.tenant_id`.

    Plano completo: `backend/docs/cota-sub-explainers-heuristicos.md`.
    """
    try:
        return await compute_explicacao_variacao(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
            threshold_brl=threshold_brl,
            top_n=top_n,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
