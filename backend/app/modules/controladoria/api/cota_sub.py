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
from app.modules.controladoria.schemas.chat_variacao import (
    ChatAgenteInfo,
    ChatVariacaoRequest,
    ChatVariacaoResposta,
)
from app.modules.controladoria.schemas.conferencia_aplicacoes import (
    ConferenciaAplicacoesResponse,
)
from app.modules.controladoria.schemas.conferencia_contas_a_pagar import (
    ConferenciaContasAPagarResponse,
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
from app.modules.controladoria.schemas.detalhamento_dia import DetalhamentoDiaResponse
from app.modules.controladoria.schemas.variacao_diaria import (
    VariacaoDiariaSeriePonto,
)
from app.modules.controladoria.schemas.variacao_headline import (
    VariacaoHeadlineResponse,
)
from app.modules.controladoria.schemas.variacao_resumo import (
    VariacaoResumoResponse,
)
from app.modules.controladoria.services.balanco_patrimonial import (
    compute_balanco_estrutural,
)
from app.modules.controladoria.services.conferencia_aplicacoes import (
    compute_movimento_aplicacoes,
)
from app.modules.controladoria.services.conferencia_contas_a_pagar import (
    compute_movimento_contas_a_pagar,
)
from app.modules.controladoria.services.conferencia_cotas import compute_movimento_cotas
from app.modules.controladoria.services.cota_sub_drill_cpr import compute_drill_cpr
from app.modules.controladoria.services.cota_sub_drill_dc import compute_drill_dc
from app.modules.controladoria.services.cota_sub_drill_origem import compute_drill_origem
from app.modules.controladoria.services.cota_sub_drill_pdd import compute_drill_pdd
from app.modules.controladoria.services.detalhamento_dia import compute_detalhamento_dia
from app.modules.controladoria.services.variacao_diaria import (
    compute_variacao_diaria_serie,
)
from app.modules.controladoria.services.variacao_headline import (
    compute_variacao_headline,
)
from app.modules.controladoria.services.variacao_resumo import (
    compute_variacao_resumo,
)
from app.modules.controladoria.services.variacoes_dia import compute_variacoes_dia
from app.modules.integracoes.public import listar_datas_disponiveis_qitech
from app.shared.ai.agent_code import derive_agent_code

router = APIRouter(prefix="/cota-sub", tags=["controladoria:cota-sub"])

_Guard = Depends(require_module(Module.CONTROLADORIA, Permission.READ))

# Agente que atende a janela de chat-investigador desta pagina. Fonte unica:
# usado pra invocar o agente E pra expor o codigo discreto na UI (GET abaixo).
_CHAT_AGENT_NAME = "controladoria.investigador_cota"


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


@router.get("/variacao/resumo", response_model=VariacaoResumoResponse)
async def variacao_resumo(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e o dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    _: None = _Guard,
) -> VariacaoResumoResponse:
    """Resumo do dia — decomposicao causal da variacao da Cota Sub por grupo de
    balanco (waterfall + detalhamento + atencoes), 100% estruturado (zero LLM).

    Os 6 grupos vem com impacto giro-limpo; Disponibilidades e o plug (Σ grupos ==
    cota_delta por construcao). Ancoras = MEC; reconciliacao expoe o residuo vs
    oficial. Substitui o /variacao/headline na aba Resumo do dia (2026-06-01).
    """
    try:
        return await compute_variacao_resumo(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/variacao/detalhamento", response_model=DetalhamentoDiaResponse)
async def variacao_detalhamento(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e o dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    _: None = _Guard,
) -> DetalhamentoDiaResponse:
    """Detalhamento do dia — o painel dos 60%. Uma area por card (Ativo/Passivo)
    com o resumo de 1 linha da sua tool + delta + drill_key. Orquestra as tools
    (compute_drill_dc, compute_drill_pdd, conferencia_*), zero LLM. Clicar um card
    abre o drill profundo daquela area.
    """
    try:
        return await compute_detalhamento_dia(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _fmt_brl(v: object) -> str:
    return f"R$ {float(v):,.0f}".replace(",", ".")


@router.post("/variacao/chat", response_model=ChatVariacaoResposta)
async def variacao_chat(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    body: ChatVariacaoRequest,
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0).")],
    _: None = _Guard,
) -> ChatVariacaoResposta:
    """Chat-investigador da variacao da Cota Sub (Camada 2, sob demanda).

    Pre-carrega o contexto estruturado do dia (headline + detalhamento) e passa
    pro agente `controladoria.investigador_cota`, que responde do contexto quando
    da e investiga com as tools (cross-reference) quando precisa. O LLM so entra
    AQUI — o read e os detalhes da pagina sao 100% estruturados.
    """
    from app.agentic._scope import ScopedContext
    from app.agentic.engine.runtime import run_standalone_agent
    from app.core.enums import Module as _Module
    from app.core.enums import Permission as _Permission

    try:
        resumo = await compute_variacao_resumo(
            db, tenant_id=principal.tenant_id, ua_id=fundo_id, data_d0=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    # Contexto estruturado pre-carregado — ORDENADO pelos 6 grupos do balanco +
    # TODAS as atencoes do deterministico + giro neutro. E o material das alavancas
    # extraordinarias do dia: o agente nao recalcula, ele le, ordena e julga o que
    # e extraordinario vs rotina (§14).
    r = resumo.reconciliacao
    linhas = [
        f"Dia analisado (D0): {resumo.data.isoformat()} (vs D-1 {resumo.data_anterior.isoformat()}).",
        f"Variacao da Cota Sub no dia: {_fmt_brl(resumo.cota_delta)}.",
        f"Reconciliacao com o MEC (oficial): "
        f"{'fecha' if r.fecha else f'NAO fecha — residuo {_fmt_brl(r.residuo)}'}.",
        "",
        "GRUPOS DO BALANCO (impacto no PL Sub, na ordem canonica DC -> PDD&WOP -> "
        "Aplicacoes -> Disponibilidades -> Obrigacoes -> Cotas Prioritarias):",
    ]
    linhas += [
        f"  - [{g.label}] impacto {_fmt_brl(g.impacto_pl_sub)} | {g.resumo}"
        for g in resumo.grupos
    ]
    if resumo.atencoes:
        linhas += ["", "ATENCOES DETECTADAS PELO DETERMINISTICO (todas — nao filtrar nenhuma):"]
        linhas += [
            f"  - [{a.tipo}] {a.descricao}: {_fmt_brl(a.valor)}"
            + (f" (grupo: {a.grupo_label})" if a.grupo_label else "")
            for a in resumo.atencoes
        ]
    if resumo.giro_capital:
        linhas += ["", "GIRO/CAPITAL DO DIA (movimentos NEUTROS — nao movem a cota em R$, contexto):"]
        linhas += [
            f"  - {gc.label}: {_fmt_brl(gc.valor)}" + (f" ({gc.nota})" if gc.nota else "")
            for gc in resumo.giro_capital
        ]
    contexto = "\n".join(linhas)

    historico = "\n".join(
        f"{'Controller' if m.role == 'user' else 'Voce'}: {m.content}" for m in body.historico
    ) or "(inicio da conversa)"

    scope = ScopedContext(
        tenant_id=principal.tenant_id,
        empresa_id=None,
        user_id=principal.user_id,
        module=_Module.CONTROLADORIA,
        permissions=dict.fromkeys(_Module, _Permission.ADMIN),
        db=db,
        extras={"ua_id": str(fundo_id), "data_d0": data.isoformat()},
    )
    result = await run_standalone_agent(
        agent_name=_CHAT_AGENT_NAME,
        scope=scope,
        user_context={
            "fundo_nome": resumo.fundo_nome,
            "data_d0": data.isoformat(),
            # Data de calendario real (referencia secundaria): permite o agente
            # distinguir "o dia selecionado na tela" (data_d0 = o 'hoje' do usuario
            # ao olhar a pagina) de "hoje de verdade", se o controller se referir
            # literalmente ao dia corrente.
            "hoje_real": date.today().isoformat(),
            "contexto": contexto,
            "historico": historico,
            "pergunta": body.pergunta,
        },
        db=db,
    )
    out = result.output_data or {}
    return ChatVariacaoResposta(
        resposta=str(out.get("resposta", "Nao consegui responder agora.")),
        tools_usadas=list(out.get("tools_usadas", []) or []),
    )


@router.get("/variacao/chat/agente", response_model=ChatAgenteInfo)
async def variacao_chat_agente(_: None = _Guard) -> ChatAgenteInfo:
    """Codigo discreto do agente que atende esta janela de chat.

    Pra UI exibir "qual agente" sem revelar o nome interno. Derivado da
    constante `_CHAT_AGENT_NAME` (mesma que invoca o agente)."""
    return ChatAgenteInfo(code=derive_agent_code(_CHAT_AGENT_NAME))


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


@router.get("/variacao-diaria", response_model=list[VariacaoDiariaSeriePonto])
async def variacao_diaria(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    competencia: Annotated[str, Query(description="Competência YYYY-MM (mês a materializar)")],
    _: None = _Guard,
) -> list[VariacaoDiariaSeriePonto]:
    """Serie diaria da variacao do PL Sub MEC na competencia — MASTER da aba
    "Resumo do dia". Um ponto por dia-calendario do mes (CLAUDE.md §14.6: nada
    cortado); dias sem snapshot vem com `variacao_cota=None`. Barato: uma leitura
    de `wh_mec_evolucao_cotas` + diff de dias uteis consecutivos (nao roda o
    waterfall por dia). Clicar num dia no frontend re-chaveia o /variacao/resumo.

    Multi-tenant: scope via `principal.tenant_id` no service.
    """
    try:
        return await compute_variacao_diaria_serie(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            competencia=competencia,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


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
        Query(description="Threshold |Δ valor_pdd| pra entrar no top papeis. Default R$ 0 "
                          "(zero ocultacao — a tabela soma EXATO a headline reversao/constituicao). "
                          "Suba so se quiser filtrar ruido conscientemente."),
    ] = Decimal("0"),
    top_n: Annotated[
        int,
        Query(ge=1, le=5000, description="Cap de papeis no top. Default 2000 (= sem corte pratico "
                                         "p/ carteira REALINVEST; alinhado com o servico/tool). "
                                         "Garante que todo papel com variacao aparece na tabela."),
    ] = 2000,
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


@router.get("/drill/contas-a-pagar", response_model=ConferenciaContasAPagarResponse)
async def drill_contas_a_pagar(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e o dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    _: None = _Guard,
) -> ConferenciaContasAPagarResponse:
    """Drill da linha Contas a Pagar — o detalhe COMPLETO do Auditor de Contas a
    Pagar (nao so a provisao).

    Duas metades + o impacto: (1) provisoes (CPR<0) por apropriacao/baixa; (2)
    PAGAMENTOS do caixa classificados por codigo do extrato, com flag de
    `provisionado`; e o campo-chave `impacto_resultado_nao_provisionado` — a
    despesa que saiu de caixa ALEM da provisao e bateu no PL Sub no dia (ex.: o
    R$ 15k do 28/05). Reusa compute_movimento_contas_a_pagar (tool do agente).
    """
    try:
        return await compute_movimento_contas_a_pagar(
            db,
            tenant_id=principal.tenant_id,
            ua_id=fundo_id,
            data_d0=data,
            data_d1=data_anterior,
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


@router.get("/drill/aplicacoes", response_model=ConferenciaAplicacoesResponse)
async def drill_aplicacoes(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID, Query(description="UUID da Unidade Administrativa (FIDC)")],
    data: Annotated[date, Query(description="Dia analisado (D0). D-1 e o dia util anterior.")],
    data_anterior: Annotated[
        date | None,
        Query(description="Override opcional para D-1."),
    ] = None,
    _: None = _Guard,
) -> ConferenciaAplicacoesResponse:
    """Drill do grupo Aplicacoes — rendimento DI (valorizacao = a barra do
    waterfall) vs capital (aplicacao/resgate de fundo DI, NEUTRO) por fundo +
    linhas menores (TPF/Compromissada/Outros). Reusa a tool do detalhamento
    (compute_movimento_aplicacoes). A barra giro-limpa bate com a soma das
    valorizacoes; o capital aparece destacado como neutro.
    """
    try:
        return await compute_movimento_aplicacoes(
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
