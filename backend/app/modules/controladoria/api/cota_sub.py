"""Controladoria · Cota Sub — endpoints."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.controladoria.schemas.agente_variacao_cota import (
    AgenteVariacaoRunMetadata,
    AgenteVariacaoRunResponse,
)
from app.modules.controladoria.schemas.conferencia_cotas import ConferenciaCotasResponse
from app.modules.controladoria.schemas.cota_sub import (
    BalancoEstruturalResponse,
    VariacoesDiaResponse,
)
from app.modules.controladoria.schemas.cota_sub_drill import (
    DrillCprResponse,
    DrillDcResponse,
    DrillOrigemResponse,
    DrillPddResponse,
)
from app.modules.controladoria.schemas.variacao_headline import (
    VariacaoHeadlineResponse,
)
from app.modules.controladoria.services.balanco_patrimonial import (
    compute_balanco_estrutural,
)
from app.modules.controladoria.services.conferencia_cotas import compute_movimento_cotas
from app.modules.controladoria.services.cota_sub_drill_cpr import compute_drill_cpr
from app.modules.controladoria.services.cota_sub_drill_dc import compute_drill_dc
from app.modules.controladoria.services.cota_sub_drill_origem import compute_drill_origem
from app.modules.controladoria.services.cota_sub_drill_pdd import compute_drill_pdd
from app.modules.controladoria.services.variacao_headline import (
    compute_variacao_headline,
)
from app.modules.controladoria.services.variacoes_dia import compute_variacoes_dia
from app.modules.integracoes.public import listar_datas_disponiveis_qitech

router = APIRouter(prefix="/cota-sub", tags=["controladoria:cota-sub"])

_Guard = Depends(require_module(Module.CONTROLADORIA, Permission.READ))


@router.get("/balanco-estrutural", response_model=BalancoEstruturalResponse)
async def balanco_estrutural(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e calculado como dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    _: None = _Guard,
) -> BalancoEstruturalResponse:
    """Balanco gerencial otica Sub Jr — coerente por natureza + sinal.

    Versao redesenhada (2026-05-27): PDD vira contra-ativo (abate DC), CPR
    dividido por sinal (a receber=ativo / a pagar=passivo), Senior+Mezanino
    agrupados como "Cotas Prioritarias", residuo MEC em bloco de reconciliacao.
    PL Sub identico ao do /balanco-patrimonial (so muda apresentacao). Aditivo:
    /balanco-patrimonial continua servindo a tool do agente (§19).
    """
    try:
        return await compute_balanco_estrutural(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/variacao/headline", response_model=VariacaoHeadlineResponse)
async def variacao_headline(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e o dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    _: None = _Guard,
) -> VariacaoHeadlineResponse:
    """Headline da variacao da Cota Sub — o read de 10s, montado SO de campos
    estruturados (zero LLM).

    Orquestra as tools (compute_balanco_estrutural, compute_drill_dc,
    compute_movimento_cotas, compute_movimento_contas_a_pagar) e entrega:
    veredito (Δ cota + reconciliacao) + drivers ranqueados por impacto LIMPO
    (giro separado do resultado, via resultado_do_dia) + flags (mutacao,
    despesa nao provisionada, capital, residuo, nao-reconhecidos).

    Substitui o trabalho do monolito (analista_variacao_cota) por algo
    deterministico, reproduzivel e auditavel (§14). O LLM (chat) so entra
    depois, sob demanda, pra investigar o que o headline aponta.
    """
    try:
        return await compute_variacao_headline(
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
    Consumido pela pagina Pagamento Diario.
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
    side: Annotated[
        Literal["receber", "pagar"] | None,
        Query(description="Segrega por sinal: 'receber' (valor>0, ativo) ou 'pagar' (valor<0, passivo). Omitido = CPR net legado."),
    ] = None,
    _: None = _Guard,
) -> DrillCprResponse:
    """Drill da categoria CPR (Contas a Pagar e Receber) do Balance hero.

    Decompoe o delta da linha CPR em:
      1. Totais D-1 / D0 / Δ
      2. Agrupamento por natureza (diferimento, taxas, despesas, IOF/IR,
         aporte/devolucao, outros)
      3. Aportes engaiolados detectados (caso pedagogico REALINVEST 07-13/05)

    `side` (2026-05-27) restringe ao lado Contas a Receber (ativo) ou Contas a
    Pagar (passivo), espelhando o split por sinal do balanco estrutural.
    """
    try:
        return await compute_drill_cpr(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
            side=side,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/drill/cotas", response_model=ConferenciaCotasResponse)
async def drill_cotas(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e o dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    _: None = _Guard,
) -> ConferenciaCotasResponse:
    """Drill das linhas de Cota/Passivo de cotista (Senior, Mezanino, Obrigacoes
    com Cotistas) — o detalhe do Auditor de Cotas.

    Decompoe as Cotas Prioritarias (Sr/Mez) em CAPITAL (aporte/resgate) vs
    VALORIZACAO (carrego que a Sub paga), e lista as Obrigacoes com Cotistas
    (CPR capital_cotista: Cotas a Resgatar, Aporte, Resgate). Reusa a mesma tool
    do agente `controladoria.auditor_cotas` (compute_movimento_cotas).
    """
    try:
        return await compute_movimento_cotas(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/drill/origem", response_model=DrillOrigemResponse)
async def drill_origem(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0).")],
    linha: Annotated[
        str,
        Query(description="Chave da linha do balanco (titulos_publicos, op_estruturadas, "
                          "fundos_di, compromissada, outros_ativos, tesouraria, "
                          "saldo_conta_corrente, senior, mezanino)."),
    ],
    _: None = _Guard,
) -> DrillOrigemResponse:
    """Drill 'ver origem' das linhas SEM drill rico (RF/Tesouraria/CC/Outros/
    Fundos/Cotas). Lista as linhas-fonte (snapshot D0) que compoem o valor da
    linha e prova o fechamento (Σ linhas == valor da linha do balanco).

    DC/PDD/CPR tem drills proprios (/drill/dc|pdd|cpr) — `linha` desses retorna 422.
    """
    try:
        return await compute_drill_origem(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            line_key=linha,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


# ─── Agente IA · analista de variacao da Cota Sub Jr ─────────────────────


@router.post(
    "/agente/analista-variacao/run",
    response_model=AgenteVariacaoRunResponse,
)
async def agente_analista_variacao_run(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e calculado como dia util anterior QiTech.")],
    _: None = _Guard,
) -> AgenteVariacaoRunResponse:
    """Invoca o agente IA de analise de variacao da Cota Sub Jr.

    Protocolo de 3 niveis executado pelo agente (Sonnet 4.6 default):
      1. Sanity check (identidade contabil PL deduzido vs PL fonte MEC)
      2. Decomposicao patrimonial (12 categorias com ΔBRL)
      3. Explicacao narrativa por categoria significativa (cita papeis,
         classifica padrao, sugere acoes)

    **Cache automatico**: invocacoes com mesmo (tenant, fundo, data, prompt
    version) servem do cache (`agent_analysis_run`). Mudanca de prompt ou
    re-ingestao de dados invalida cache automaticamente.

    Custo tipico: R$ 1,40 por execucao nova (Sonnet 4.6); R$ 0 em cache hit.
    Duracao tipica: ~90s execucao nova; <1s cache hit.

    Multi-tenant: scope enforced via `principal.tenant_id`.
    Audit: row gravada em `agent_analysis_run` com audit_version composto +
    tokens + custo estimado + status.
    """
    # Imports tardios pra evitar carregar o motor agentico em endpoints que
    # nao usam (startup mais rapido).
    from sqlalchemy import select as sa_select

    from app.agentic._scope import ScopedContext
    from app.agentic.engine.runtime import run_standalone_agent
    from app.modules.cadastros.public import UnidadeAdministrativa
    from app.modules.integracoes.public import dia_util_anterior_qitech

    # Resolve UA + dia util anterior (mesmo padrao dos drills).
    ua = (
        await db.execute(
            sa_select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == principal.tenant_id)
            .where(UnidadeAdministrativa.id == fundo_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unidade Administrativa {fundo_id} nao encontrada.",
        )

    data_anterior = await dia_util_anterior_qitech(
        db, tenant_id=principal.tenant_id, ua_id=fundo_id, data_d0=data,
    )

    scope = ScopedContext(
        tenant_id=principal.tenant_id,
        empresa_id=None,
        user_id=principal.user_id,
        module=Module.CONTROLADORIA,
        permissions={Module.CONTROLADORIA: Permission.READ},
        db=db,
        extras={
            "ua_id": str(fundo_id),
            "data_d0": data.isoformat(),
        },
    )
    user_context = {
        "fundo_nome": ua.nome,
        "data_d0": data.isoformat(),
        "data_anterior": data_anterior.isoformat(),
    }

    try:
        result = await run_standalone_agent(
            agent_name="controladoria.analista_variacao_cota",
            scope=scope,
            user_context=user_context,
            db=db,
        )
    except Exception as exc:  # pragma: no cover — falha rara
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao invocar agente: {exc}",
        ) from exc

    return AgenteVariacaoRunResponse(
        metadata=AgenteVariacaoRunMetadata(
            analysis_run_id=result.analysis_run_id,
            audit_version=result.prompt_full_id,
            model_used=result.model_used,
            from_cache=result.from_cache,
            cache_age_seconds=result.cache_age_seconds,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            tokens_cache_read=result.tokens_cache_read,
            tokens_cache_creation=result.tokens_cache_creation,
            cost_brl_estimated=result.cost_brl,
            duration_ms=result.duration_ms,
        ),
        analise=result.output_data,  # type: ignore[arg-type]  # Pydantic valida ao serializar
    )


@router.post("/agente/analista-variacao/run-stream")
async def agente_analista_variacao_run_stream(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e calculado como dia util anterior QiTech.")],
    _: None = _Guard,
):
    """Versao SSE de `/agente/analista-variacao/run` — streama o trabalho do agente ao vivo.

    Em vez de bloquear ~90s e devolver o JSON inteiro, emite frames
    `text/event-stream` conforme o agente raciocina:

      - `event: step`   — um SessionStep (tool_use / tool_result / reasoning /
                          observation / error) no shape `AgentToolLogEntry`
                          (iso_at, kind, tool_name, duration_ms, message).
                          Alimenta o `<AgentLiveStatus>` no frontend.
      - `event: result` — payload final (mesmo shape de `AgenteVariacaoRunResponse`).
      - `event: error`  — falha durante a execucao (a resposta HTTP ja e 200;
                          o erro vai no corpo do stream, como em /ai/chat).

    Cache hit: nenhum `step` e emitido (o agente retorna do cache sem rodar
    tools); apenas um `result` chega quase instantaneo.

    Multi-tenant + audit: identicos ao endpoint nao-streaming (mesmo
    `run_standalone_agent`, mesma row em `agent_analysis_run`).
    """
    import asyncio
    import contextlib
    import json as _json
    from collections.abc import AsyncIterator

    from fastapi.responses import StreamingResponse
    from sqlalchemy import select as sa_select

    from app.agentic._scope import ScopedContext
    from app.agentic.engine.runtime import run_standalone_agent
    from app.agentic.memory._base import create_session
    from app.modules.cadastros.public import UnidadeAdministrativa
    from app.modules.integracoes.public import dia_util_anterior_qitech

    # Resolve UA + dia util anterior ANTES de abrir o stream — assim um 404
    # vira HTTP 404 de verdade (e nao um frame de erro dentro de um 200).
    ua = (
        await db.execute(
            sa_select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == principal.tenant_id)
            .where(UnidadeAdministrativa.id == fundo_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unidade Administrativa {fundo_id} nao encontrada.",
        )

    data_anterior = await dia_util_anterior_qitech(
        db, tenant_id=principal.tenant_id, ua_id=fundo_id, data_d0=data,
    )

    scope = ScopedContext(
        tenant_id=principal.tenant_id,
        empresa_id=None,
        user_id=principal.user_id,
        module=Module.CONTROLADORIA,
        permissions={Module.CONTROLADORIA: Permission.READ},
        db=db,
        extras={
            "ua_id": str(fundo_id),
            "data_d0": data.isoformat(),
        },
    )
    user_context = {
        "fundo_nome": ua.nome,
        "data_d0": data.isoformat(),
        "data_anterior": data_anterior.isoformat(),
    }

    # Session in-memory cujo `_on_step` empurra cada step pra fila — o runtime
    # ja chama record_tool_use/result/reasoning, entao o trace flui sem mexer
    # no motor. Sem persistencia anexada (a row de audit ja e gravada por
    # run_standalone_agent); o trace ao vivo e efemero.
    session = create_session(
        tenant_id=principal.tenant_id,
        started_by_user_id=principal.user_id,
        module=Module.CONTROLADORIA,
        context_label=f"cota-sub-variacao:{fundo_id}:{data.isoformat()}",
    )
    queue: asyncio.Queue = asyncio.Queue()

    def _on_step(step) -> None:
        # Sync callback rodando no event loop — put_nowait nunca bloqueia
        # (fila ilimitada). to_log_entry() = shape AgentToolLogEntry.
        with contextlib.suppress(Exception):  # nao pode quebrar o runtime
            queue.put_nowait(("step", step.to_log_entry()))

    session._on_step = _on_step

    async def _run_agent() -> None:
        try:
            result = await run_standalone_agent(
                agent_name="controladoria.analista_variacao_cota",
                scope=scope,
                user_context=user_context,
                db=db,
                session=session,
            )
            resp = AgenteVariacaoRunResponse(
                metadata=AgenteVariacaoRunMetadata(
                    analysis_run_id=result.analysis_run_id,
                    audit_version=result.prompt_full_id,
                    model_used=result.model_used,
                    from_cache=result.from_cache,
                    cache_age_seconds=result.cache_age_seconds,
                    tokens_input=result.tokens_input,
                    tokens_output=result.tokens_output,
                    tokens_cache_read=result.tokens_cache_read,
                    tokens_cache_creation=result.tokens_cache_creation,
                    cost_brl_estimated=result.cost_brl,
                    duration_ms=result.duration_ms,
                ),
                analise=result.output_data,  # type: ignore[arg-type]
            )
            await queue.put(("result", resp.model_dump(mode="json")))
        except Exception as exc:  # pragma: no cover — falha rara
            await queue.put(("error", {"detail": f"{type(exc).__name__}: {exc}"}))
        finally:
            await queue.put(("__end__", None))

    async def event_stream() -> AsyncIterator[bytes]:
        task = asyncio.create_task(_run_agent())
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "__end__":
                    break
                frame = f"event: {kind}\ndata: {_json.dumps(payload, ensure_ascii=False)}\n\n"
                yield frame.encode("utf-8")
        finally:
            # Cliente desconectou no meio (generator cancelado): cancela o
            # agente pra nao deixar a chamada LLM orfa rodando.
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
