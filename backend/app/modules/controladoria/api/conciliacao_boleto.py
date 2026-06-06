"""Controladoria · Conciliacao de boletos (Banco Cobrador) — endpoints.

L2 Conciliacoes > Banco Cobrador. Cruza a carteira Bitfin atual (titulos
abertos elegiveis a boleto) com a cobranca vigente (boletos ativos). Estado-vs-
estado, sem data-base; a defasagem do banco vai como frescor.

Auth: require_module(CONTROLADORIA, READ). Tenant scope via principal.
"""

import asyncio
import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.controladoria.schemas.conciliacao_boleto import (
    ConciliacaoBancoCobradorResponse,
    LinhaConciliacaoSchema,
    ResumoStatus,
)
from app.modules.controladoria.services.conciliacao_boleto import (
    ConciliacaoBoletoResult,
    LinhaConciliacao,
    conciliar_boletos,
)

router = APIRouter(
    prefix="/conciliacao/banco-cobrador", tags=["controladoria:conciliacao-boleto"]
)

_Guard = Depends(require_module(Module.CONTROLADORIA, Permission.READ))
# Disparar a coleta/reprocessamento e acao de escrita (ingere arquivos + reescreve
# a vigente). Exige WRITE; READ basta para visualizar a conciliacao.
_GuardWrite = Depends(require_module(Module.CONTROLADORIA, Permission.WRITE))


def _mapear_linha(linha: LinhaConciliacao) -> LinhaConciliacaoSchema:
    diferenca_valor: Decimal | None = None
    if linha.valor_bitfin is not None and linha.valor_banco is not None:
        diferenca_valor = linha.valor_banco - linha.valor_bitfin
    diferenca_dias: int | None = None
    if linha.venc_bitfin is not None and linha.venc_banco is not None:
        diferenca_dias = (linha.venc_banco - linha.venc_bitfin).days
    return LinhaConciliacaoSchema(
        status=linha.status,
        numero=linha.numero,
        nosso_numero=linha.nosso_numero,
        valor_bitfin=linha.valor_bitfin,
        valor_banco=linha.valor_banco,
        diferenca_valor=diferenca_valor,
        venc_bitfin=linha.venc_bitfin,
        venc_banco=linha.venc_banco,
        data_operacao=linha.data_operacao,
        diferenca_dias=diferenca_dias,
        produto=linha.produto,
        banco=linha.banco,
        cedente_documento=linha.cedente_documento,
        cedente_nome=linha.cedente_nome,
        ua_id=linha.ua_id,
        ua_nome=linha.ua_nome,
    )


def _resumir(result: ConciliacaoBoletoResult) -> list[ResumoStatus]:
    total = len(result.linhas) or 1
    qtd: dict[str, int] = defaultdict(int)
    vb: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    vbanco: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for linha in result.linhas:
        qtd[linha.status] += 1
        if linha.valor_bitfin is not None:
            vb[linha.status] += linha.valor_bitfin
        if linha.valor_banco is not None:
            vbanco[linha.status] += linha.valor_banco
    return [
        ResumoStatus(
            status=s,  # type: ignore[arg-type]
            quantidade=qtd[s],
            percentual=round(qtd[s] * 100 / total, 1),
            valor_bitfin=vb[s],
            valor_banco=vbanco[s],
            diferenca=vbanco[s] - vb[s],
        )
        for s in sorted(qtd, key=lambda s: qtd[s], reverse=True)
    ]


@router.get("", response_model=ConciliacaoBancoCobradorResponse)
async def conciliacao_banco_cobrador(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _Guard,
) -> ConciliacaoBancoCobradorResponse:
    """Conciliacao titulo-a-titulo: carteira BITFIN atual x cobranca vigente.

    Estado-vs-estado (sem data-base). Resumo consolidado por status + linhas. O
    front escopa por UA e aplica filtros do tenant (ex.: Pedreira so-CBV na A7).
    """
    result = await conciliar_boletos(db, tenant_id=principal.tenant_id)
    return ConciliacaoBancoCobradorResponse(
        cobranca_atualizada_ate=result.cobranca_atualizada_ate,
        titulos_abertos=result.titulos_abertos,
        boletos_ativos=result.boletos_ativos,
        conciliados=result.conciliados,
        resumo=_resumir(result),
        linhas=[_mapear_linha(linha) for linha in result.linhas],
    )


_RUNNING_SYNC: set[asyncio.Task] = set()  # ref forte p/ evitar GC (reap do filho)


@router.post("/sync", status_code=202)
async def disparar_sync(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    _: None = _GuardWrite,
) -> dict:
    """Dispara a coleta/reprocessamento da cobranca para o TENANT (botao da
    pagina). Le os arquivos CNAB da inbox -> bronze -> timeline -> vigente. Banco
    e UA saem dos arquivos/titulos: o usuario NAO define UA.

    O ciclo e CPU-bound (~45s) -- roda como SUBPROCESS detached (nao no event
    loop do gr-api, que congelaria todos os requests). Retorna 202 imediatamente;
    o front re-busca a conciliacao apos alguns segundos. `start_new_session`
    desacopla do ciclo de vida do gr-api.
    """
    backend_root = Path(__file__).resolve().parents[4]  # .../backend
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "scripts.run_cobranca_sync",
        str(principal.tenant_id),
        cwd=str(backend_root),
        env=os.environ.copy(),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    # Reap em background (nao bloqueia a resposta) -- evita zumbi quando termina.
    task = asyncio.create_task(proc.wait())
    _RUNNING_SYNC.add(task)
    task.add_done_callback(_RUNNING_SYNC.discard)
    return {"status": "iniciado"}
