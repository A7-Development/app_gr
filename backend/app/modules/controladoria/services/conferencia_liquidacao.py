"""Controladoria · Conferencia de liquidacao — entrada de caixa por liquidacao.

Reconcilia o caixa que ENTROU por liquidacao de recebiveis com as liquidacoes
que o originaram. Ver schema (conferencia_liquidacao.py) pro racional completo.

Espinha PRA TRAS (point-in-time): o bucket `LIQUIDADOS TOTAL - PROV` de D0 (caixa
de floating que pingou hoje) e decomposto em lotes; cada lote casa por VALOR com
a Σ `LIQUIDAÇÃO NORMAL` de um dia de pregao anterior (d+1 util, as vezes d+2).
Casamento por valor (nao por calendario) — robusto a feriados.

Silver-only (§13.2.1): le wh_liquidacao_recebivel + wh_movimento_caixa + wh_extrato_bancario.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.conferencia_liquidacao import (
    ConferenciaLiquidacaoResponse,
    LiquidacaoPorTipo,
    LoteFloating,
)
from app.warehouse.extrato_bancario import ExtratoBancario
from app.warehouse.liquidacao_recebivel import LiquidacaoRecebivel
from app.warehouse.movimento_caixa import MovimentoCaixa

ZERO = Decimal("0")
_MATCH_TOL = Decimal("0.01")

_TIPO_SACADO = "BAIXA POR DEPOSITO SACADO"
_TIPOS_HONRA_CEDENTE = ("BAIXA POR DEPOSITO CEDENTE", "BAIXA POR RECOMPRA")
# Tipos que FLOATAM pro bucket PROV (cobranca que liquida d+1 util). Achado
# empirico 2026-05-30: alem da NORMAL, o CARTÓRIO tambem floata — PROV(20/05)
# incluiu NORMAL+CARTÓRIO de 19/05 (387.874,47 = 386.950,90 + 923,57). PARCIAL
# entra por simetria (cobranca, raro). DEPOSITO SACADO NAO floata (imediato).
_TIPOS_FLOATING = (
    "LIQUIDAÇÃO NORMAL",
    "LIQUIDAÇÃO EM CARTÓRIO",
    "LIQUIDAÇÃO PARCIAL",
)
_DESCR_PROV = "LIQUIDADOS TOTAL - PROV"

# Janela (dias corridos) varrida pra tras procurando o dia-origem de um lote PROV.
# d+1 util cobre ate Sex->Seg (3 corridos); d+2 raro. 7 e folga confortavel.
_JANELA_ORIGEM_DIAS = 7


async def compute_conferencia_liquidacao(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
) -> ConferenciaLiquidacaoResponse:
    """Confere a entrada de caixa por liquidacao do dia D0.

    Raises:
        ValueError: quando a UA nao existe.
    """
    ua = (
        await db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise ValueError(f"Unidade Administrativa {ua_id} nao encontrada")

    fundo_doc = ua.cnpj or ""

    def _scope_liq(stmt):
        return stmt.where(
            (LiquidacaoRecebivel.unidade_administrativa_id == ua_id)
            | (
                (LiquidacaoRecebivel.unidade_administrativa_id.is_(None))
                & (LiquidacaoRecebivel.fundo_doc == fundo_doc)
            )
        )

    # ── Liquidacoes do dia por tipo_movimento ───────────────────────────────
    atrasado = LiquidacaoRecebivel.data_posicao > LiquidacaoRecebivel.data_vencimento
    tipo_rows = (
        await db.execute(
            _scope_liq(
                select(
                    LiquidacaoRecebivel.tipo_movimento,
                    func.count().label("n"),
                    func.coalesce(func.sum(LiquidacaoRecebivel.valor_pago), ZERO).label("total"),
                    func.coalesce(
                        func.sum(case((atrasado, 1), else_=0)), 0
                    ).label("n_atrasados"),
                )
                .where(LiquidacaoRecebivel.tenant_id == tenant_id)
                .where(LiquidacaoRecebivel.data_posicao == data_d0)
                .group_by(LiquidacaoRecebivel.tipo_movimento)
            )
        )
    ).all()

    liquidacoes_por_tipo: list[LiquidacaoPorTipo] = []
    total_liquidado = ZERO
    floating_hoje = sacado_hoje = honra_total = ZERO
    honra_n = honra_atrasados = 0
    for r in tipo_rows:
        valor = Decimal(r.total)
        total_liquidado += valor
        liquidacoes_por_tipo.append(
            LiquidacaoPorTipo(
                tipo_movimento=r.tipo_movimento,
                n=int(r.n or 0),
                valor_pago=valor,
                n_atrasados=int(r.n_atrasados or 0),
            )
        )
        if r.tipo_movimento in _TIPOS_FLOATING:
            floating_hoje += valor
        elif r.tipo_movimento == _TIPO_SACADO:
            sacado_hoje = valor
        elif r.tipo_movimento in _TIPOS_HONRA_CEDENTE:
            honra_total += valor
            honra_n += int(r.n or 0)
            honra_atrasados += int(r.n_atrasados or 0)
    liquidacoes_por_tipo.sort(key=lambda t: -t.valor_pago)

    # ── Floating por dia (D0-janela .. D0) — pra casar os lotes PROV ─────────
    # Soma das cobrancas que floatam (NORMAL + CARTÓRIO + PARCIAL) por dia.
    norm_rows = (
        await db.execute(
            _scope_liq(
                select(
                    LiquidacaoRecebivel.data_posicao,
                    func.coalesce(func.sum(LiquidacaoRecebivel.valor_pago), ZERO).label("total"),
                )
                .where(LiquidacaoRecebivel.tenant_id == tenant_id)
                .where(LiquidacaoRecebivel.tipo_movimento.in_(_TIPOS_FLOATING))
                .where(LiquidacaoRecebivel.data_posicao >= data_d0 - timedelta(days=_JANELA_ORIGEM_DIAS))
                .where(LiquidacaoRecebivel.data_posicao < data_d0)
                .group_by(LiquidacaoRecebivel.data_posicao)
            )
        )
    ).all()
    prior_normal: dict[date, Decimal] = {r.data_posicao: Decimal(r.total) for r in norm_rows}

    # Dia de pregao anterior (mais recente < D0 com qualquer liquidacao).
    data_anterior_util = (
        await db.execute(
            _scope_liq(
                select(func.max(LiquidacaoRecebivel.data_posicao))
                .where(LiquidacaoRecebivel.tenant_id == tenant_id)
                .where(LiquidacaoRecebivel.data_posicao < data_d0)
            )
        )
    ).scalar_one_or_none()

    # ── Disponibilidades: saldo de fechamento (Tesouraria + Conta Corrente) ──
    # O Auditor de Caixa "assume" a Tesouraria (decisao 2026-05-31): e o residuo
    # do fluxo do dia. Imaterial na REALINVEST (sobra <~R$ 1k). Lazy import pra
    # evitar ciclo de import com cota_sub/balanco_patrimonial.
    from app.modules.controladoria.services.balanco_patrimonial import (
        _sum_saldo_conta_corrente,
    )
    from app.modules.controladoria.services.cota_sub import _sum_tesouraria

    tes_d0 = await _sum_tesouraria(db, tenant_id, ua_id, data_d0)
    cc_d0 = await _sum_saldo_conta_corrente(db, tenant_id, ua_id, data_d0)
    if data_anterior_util:
        tes_d1 = await _sum_tesouraria(db, tenant_id, ua_id, data_anterior_util)
        cc_d1 = await _sum_saldo_conta_corrente(db, tenant_id, ua_id, data_anterior_util)
    else:
        tes_d1 = cc_d1 = ZERO

    # ── Bucket PROV de D0 (caixa de floating que caiu hoje) ──────────────────
    prov_rows = (
        await db.execute(
            select(MovimentoCaixa.entradas)
            .where(MovimentoCaixa.tenant_id == tenant_id)
            .where(MovimentoCaixa.descricao == _DESCR_PROV)
            .where(func.date(MovimentoCaixa.data_liquidacao) == data_d0)
            .where(
                (MovimentoCaixa.unidade_administrativa_id == ua_id)
                | (MovimentoCaixa.unidade_administrativa_id.is_(None))
            )
        )
    ).all()
    prov_total = sum((Decimal(r.entradas) for r in prov_rows), ZERO)
    lote_valores = sorted(
        (Decimal(r.entradas) for r in prov_rows if Decimal(r.entradas) > ZERO),
        reverse=True,
    )

    # Casamento greedy: cada lote -> dia anterior (mais recente livre) cuja
    # Σ NORMAL bate o valor do lote (tolerancia de centavos).
    prov_lotes: list[LoteFloating] = []
    usados: set[date] = set()
    matched_sum = ZERO
    for valor in lote_valores:
        achou: date | None = None
        for d in sorted(prior_normal, reverse=True):
            if d in usados:
                continue
            if abs(prior_normal[d] - valor) < _MATCH_TOL:
                achou = d
                break
        if achou is not None:
            usados.add(achou)
            matched_sum += valor
            prov_lotes.append(
                LoteFloating(
                    valor=valor,
                    dia_origem=achou,
                    defasagem_dias=(data_d0 - achou).days,
                    normal_origem=prior_normal[achou],
                    status="casa",
                )
            )
        else:
            prov_lotes.append(LoteFloating(valor=valor, status="origem_nao_identificada"))

    floating_residuo = prov_total - matched_sum
    floating_status = "casa" if abs(floating_residuo) < _MATCH_TOL else "diverge"

    # ── Extrato (contexto agregado da perna SACADO imediata) ────────────────
    ext_max = (
        await db.execute(
            select(func.max(ExtratoBancario.data_lancamento)).where(
                ExtratoBancario.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    extrato_disponivel = ext_max is not None and ext_max >= data_d0
    extrato_credito_dia: Decimal | None = None
    if extrato_disponivel:
        extrato_credito_dia = (
            await db.execute(
                select(func.coalesce(func.sum(ExtratoBancario.valor), ZERO))
                .where(ExtratoBancario.tenant_id == tenant_id)
                .where(ExtratoBancario.tipo == "C")
                .where(ExtratoBancario.data_lancamento == data_d0)
                .where(
                    (ExtratoBancario.unidade_administrativa_id == ua_id)
                    | (ExtratoBancario.unidade_administrativa_id.is_(None))
                )
            )
        ).scalar_one()

    return ConferenciaLiquidacaoResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior_util=data_anterior_util,
        liquidacoes_por_tipo=liquidacoes_por_tipo,
        total_liquidado=total_liquidado,
        prov_total=prov_total,
        prov_lotes=prov_lotes,
        floating_residuo=floating_residuo,
        floating_status=floating_status,
        sacado_hoje=sacado_hoje,
        extrato_disponivel=extrato_disponivel,
        extrato_credito_dia=extrato_credito_dia,
        extrato_ultimo_lancamento=ext_max,
        honra_cedente_total=honra_total,
        honra_cedente_n=honra_n,
        honra_cedente_todos_atrasados=(honra_n > 0 and honra_atrasados == honra_n),
        floating_hoje=floating_hoje,
        tesouraria_d0=tes_d0,
        tesouraria_delta=tes_d0 - tes_d1,
        conta_corrente_d0=cc_d0,
        conta_corrente_delta=cc_d0 - cc_d1,
    )
