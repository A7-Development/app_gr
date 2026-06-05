"""Controladoria · Conciliacao de boletos (Banco Cobrador) — endpoints.

L2 Conciliacoes > Banco Cobrador. Cruza a carteira Bitfin (titulos abertos
elegiveis a boleto) com os boletos ativos dos bancos cobradores numa data-base.

Auth: require_module(CONTROLADORIA, READ). Tenant scope via principal.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
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
    listar_datas_disponiveis,
)

router = APIRouter(
    prefix="/conciliacao/banco-cobrador", tags=["controladoria:conciliacao-boleto"]
)

_Guard = Depends(require_module(Module.CONTROLADORIA, Permission.READ))


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
        valor_bitfin=linha.valor_bitfin,
        valor_banco=linha.valor_banco,
        diferenca_valor=diferenca_valor,
        venc_bitfin=linha.venc_bitfin,
        venc_banco=linha.venc_banco,
        diferenca_dias=diferenca_dias,
        produto=linha.produto,
        banco=linha.banco,
        cedente_documento=linha.cedente_documento,
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
    data_ref: Annotated[
        date, Query(description="Data-base da conciliacao (dia do retorno).")
    ],
    _: None = _Guard,
) -> ConciliacaoBancoCobradorResponse:
    """Conciliacao titulo-a-titulo carteira x boletos na data-base.

    Resumo consolidado por status + linhas. O front segmenta por status e
    aplica filtros do tenant (ex.: Pedreira so-CBV na A7).
    """
    result = await conciliar_boletos(
        db, tenant_id=principal.tenant_id, data_ref=data_ref
    )
    return ConciliacaoBancoCobradorResponse(
        data_ref=result.data_ref,
        titulos_abertos=result.titulos_abertos,
        boletos_ativos=result.boletos_ativos,
        conciliados=result.conciliados,
        resumo=_resumir(result),
        linhas=[_mapear_linha(linha) for linha in result.linhas],
    )


@router.get("/datas", response_model=list[date])
async def datas_disponiveis(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _Guard,
) -> list[date]:
    """Datas-base com boletos ingeridos (para o seletor da pagina)."""
    return await listar_datas_disponiveis(db, tenant_id=principal.tenant_id)
