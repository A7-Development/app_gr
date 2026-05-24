"""Controladoria · Cota Sub · drill DC (F2 do redesign, 2026-05-23).

Decompoe a categoria DC (Direitos Creditorios) do Balance hero em:

  1. Aquisicoes do dia      — linhas de `wh_aquisicao_recebivel` em D0
  2. Liquidacoes por tipo   — `wh_liquidacao_recebivel` em D0, agrupado por
                               `tipo_movimento` (LIQUIDAÇÃO NORMAL, BAIXA,
                               RECOMPRA, etc.)
  3. Apropriacao derivada   — formula explicita:
                               apropriacao = ΔEstoque + Liquidacoes - Aquisicoes

ΔEstoque vem do CONSOLIDADO (via `_sum_dc` de cota_sub.py — Σ
`wh_posicao_cota_fundo` dos fundos internos do FIDC), nao do granular
`wh_estoque_recebivel`. Razao: o que o usuario clicou no Balance hero
e a linha consolidada — o drill explica o delta dessa linha, nao um
outro qualquer.

Liquidacoes saem do estoque ao `valor_aquisicao` (custo no FIDC). O
`ganho_liquido` (valor_pago - valor_aquisicao - ajuste) NAO entra na
apropriacao — vai pra Tesouraria como caixa recebido alem do custo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub_drill import (
    DrillDcApropriacao,
    DrillDcAquisicao,
    DrillDcLiquidacaoLinha,
    DrillDcLiquidacaoPorTipo,
    DrillDcResponse,
)
from app.modules.controladoria.services.cota_sub import _sum_dc
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.aquisicao_recebivel import AquisicaoRecebivel
from app.warehouse.liquidacao_recebivel import LiquidacaoRecebivel

ZERO = Decimal("0")

# Top N liquidacoes individuais retornadas (ordenadas por |valor_pago| DESC).
# 30 cobre dia tipico em REALINVEST (~10-20 liquidacoes); UI corta visual.
_TOP_LIQUIDACOES_N = 30


async def _aquisicoes_do_dia(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    fundo_doc: str,
    data: date,
) -> tuple[list[DrillDcAquisicao], int, Decimal]:
    """Aquisicoes (linha do `wh_aquisicao_recebivel` com data_aquisicao = D0).

    Filtra por `unidade_administrativa_id` quando presente; cai pra `fundo_doc`
    em linhas legacy (pre Phase F multi-UA). Mesmo padrao do
    `cota_sub_explainers._movimento_carteira_evidencias`.
    """
    stmt = (
        select(AquisicaoRecebivel)
        .where(AquisicaoRecebivel.tenant_id == tenant_id)
        .where(AquisicaoRecebivel.data_aquisicao == data)
        .where(
            (AquisicaoRecebivel.unidade_administrativa_id == ua_id)
            | (
                (AquisicaoRecebivel.unidade_administrativa_id.is_(None))
                & (AquisicaoRecebivel.fundo_doc == fundo_doc)
            )
        )
        .order_by(AquisicaoRecebivel.valor_compra.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    aquisicoes = [
        DrillDcAquisicao(
            cedente_doc=row.cedente_doc,
            cedente_nome=row.cedente_nome,
            sacado_doc=row.sacado_doc,
            sacado_nome=row.sacado_nome,
            seu_numero=row.seu_numero,
            numero_documento=row.numero_documento,
            tipo_recebivel=row.tipo_recebivel,
            data_vencimento=row.data_vencimento,
            valor_compra=row.valor_compra,
            valor_vencimento=row.valor_vencimento,
            taxa_aquisicao=row.taxa_aquisicao,
            prazo_recebivel=row.prazo_recebivel,
        )
        for row in rows
    ]
    total = sum((a.valor_compra for a in aquisicoes), ZERO)
    return aquisicoes, len(aquisicoes), total


async def _liquidacoes_do_dia(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    fundo_doc: str,
    data: date,
) -> tuple[list[DrillDcLiquidacaoPorTipo], list[DrillDcLiquidacaoLinha], int, Decimal]:
    """Liquidacoes do dia + agrupamento por `tipo_movimento` + top N individuais.

    Retorna (por_tipo, top_individuais, qtd_total, total_valor_aquisicao).
    `total_valor_aquisicao` e o que sai do estoque (custo no FIDC); usado
    na formula da apropriacao.
    """
    base = (
        select(LiquidacaoRecebivel)
        .where(LiquidacaoRecebivel.tenant_id == tenant_id)
        .where(LiquidacaoRecebivel.data_posicao == data)
        .where(
            (LiquidacaoRecebivel.unidade_administrativa_id == ua_id)
            | (
                (LiquidacaoRecebivel.unidade_administrativa_id.is_(None))
                & (LiquidacaoRecebivel.fundo_doc == fundo_doc)
            )
        )
    )

    # Aggregate por tipo_movimento numa unica passada.
    agg_stmt = (
        select(
            LiquidacaoRecebivel.tipo_movimento,
            func.count().label("qtd"),
            func.coalesce(func.sum(LiquidacaoRecebivel.valor_pago), ZERO).label("sum_pago"),
            func.coalesce(func.sum(LiquidacaoRecebivel.valor_aquisicao), ZERO).label("sum_aq"),
            func.coalesce(func.sum(LiquidacaoRecebivel.valor_vencimento), ZERO).label("sum_venc"),
            func.coalesce(func.sum(LiquidacaoRecebivel.ajuste), ZERO).label("sum_aj"),
        )
        .where(LiquidacaoRecebivel.tenant_id == tenant_id)
        .where(LiquidacaoRecebivel.data_posicao == data)
        .where(
            (LiquidacaoRecebivel.unidade_administrativa_id == ua_id)
            | (
                (LiquidacaoRecebivel.unidade_administrativa_id.is_(None))
                & (LiquidacaoRecebivel.fundo_doc == fundo_doc)
            )
        )
        .group_by(LiquidacaoRecebivel.tipo_movimento)
        .order_by(func.sum(LiquidacaoRecebivel.valor_pago).desc())
    )
    agg_rows = (await db.execute(agg_stmt)).all()

    por_tipo: list[DrillDcLiquidacaoPorTipo] = []
    qtd_total = 0
    sum_aquisicao_total = ZERO
    for tipo, qtd, sum_pago, sum_aq, sum_venc, sum_aj in agg_rows:
        sum_pago_d = Decimal(sum_pago or 0)
        sum_aq_d = Decimal(sum_aq or 0)
        sum_aj_d = Decimal(sum_aj or 0)
        qtd_total += int(qtd or 0)
        sum_aquisicao_total += sum_aq_d
        por_tipo.append(
            DrillDcLiquidacaoPorTipo(
                tipo_movimento=tipo or "—",
                qtd_papeis=int(qtd or 0),
                sum_valor_pago=sum_pago_d,
                sum_valor_aquisicao=sum_aq_d,
                sum_valor_vencimento=Decimal(sum_venc or 0),
                sum_ajuste=sum_aj_d,
                ganho_liquido=sum_pago_d - sum_aq_d - sum_aj_d,
            )
        )

    # Top N individuais por valor_pago.
    top_stmt = base.order_by(LiquidacaoRecebivel.valor_pago.desc()).limit(_TOP_LIQUIDACOES_N)
    top_rows = (await db.execute(top_stmt)).scalars().all()

    top_individuais = [
        DrillDcLiquidacaoLinha(
            cedente_doc=r.cedente_doc,
            cedente_nome=r.cedente_nome,
            sacado_doc=r.sacado_doc,
            sacado_nome=r.sacado_nome,
            seu_numero=r.seu_numero,
            documento=r.documento,
            tipo_recebivel=r.tipo_recebivel,
            tipo_movimento=r.tipo_movimento,
            valor_pago=r.valor_pago,
            valor_aquisicao=r.valor_aquisicao,
            valor_vencimento=r.valor_vencimento,
            ajuste=r.ajuste,
            ganho_liquido=r.valor_pago - r.valor_aquisicao - r.ajuste,
        )
        for r in top_rows
    ]

    return por_tipo, top_individuais, qtd_total, sum_aquisicao_total


async def compute_drill_dc(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> DrillDcResponse:
    """Drill DC: aquisicoes + liquidacoes por tipo + apropriacao derivada.

    Args:
        tenant_id: escopo multi-tenant.
        ua_id: UUID da UA (FIDC).
        data_d0: dia analisado.
        data_d1: override opcional de D-1.

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

    d1 = data_d1 or await dia_util_anterior_qitech(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )

    # Estoque consolidado (mesma fonte do Balance hero — Σ wh_posicao_cota_fundo
    # dos fundos internos do FIDC).
    estoque_d1 = await _sum_dc(db, tenant_id, ua_id, ua.nome, d1)
    estoque_d0 = await _sum_dc(db, tenant_id, ua_id, ua.nome, data_d0)

    aquisicoes, aquisicoes_qtd, aquisicoes_total = await _aquisicoes_do_dia(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        fundo_doc=ua.cnpj or "",
        data=data_d0,
    )

    por_tipo, top_liq, liquidacoes_qtd, liquidacoes_total = await _liquidacoes_do_dia(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        fundo_doc=ua.cnpj or "",
        data=data_d0,
    )

    delta_estoque = estoque_d0 - estoque_d1
    apropriacao_val = delta_estoque + liquidacoes_total - aquisicoes_total

    return DrillDcResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior=d1,
        aquisicoes_qtd=aquisicoes_qtd,
        aquisicoes_total=aquisicoes_total,
        aquisicoes=aquisicoes,
        liquidacoes_qtd=liquidacoes_qtd,
        liquidacoes_total=liquidacoes_total,
        liquidacoes_por_tipo=por_tipo,
        liquidacoes_top=top_liq,
        apropriacao=DrillDcApropriacao(
            estoque_d1=estoque_d1,
            estoque_d0=estoque_d0,
            delta_estoque=delta_estoque,
            aquisicoes_total=aquisicoes_total,
            liquidacoes_total=liquidacoes_total,
            apropriacao=apropriacao_val,
        ),
    )
