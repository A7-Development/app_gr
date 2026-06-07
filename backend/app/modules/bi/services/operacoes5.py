"""BI — service da pagina /bi/operacoes5 (espinha de drill por dimensao).

Tres niveis da espinha UA -> Produto -> Cedente -> Operacao -> Documento
(Sacado entra na Fase 2). Regime CAIXA (wh_operacao + wh_titulo), reaproveita
os helpers de `services/operacoes.py` (_apply_filters, _weighted_avg,
_produto_expr, _receita_total_expr, _build_provenance) — mesma matematica da
operacoes4, garantindo numeros consistentes entre as paginas.

Reconciliacao (CLAUDE.md §14.6): cada bundle retorna o total somado das linhas
exibidas (vop_total / valor_total) — sem corte silencioso, sem top-N.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bi.schemas.common import Provenance
from app.modules.bi.schemas.operacoes5 import (
    Operacoes5CedenteItem,
    Operacoes5CedentesData,
    Operacoes5DocumentoItem,
    Operacoes5DocumentosData,
    Operacoes5OperacaoItem,
    Operacoes5OperacoesData,
)
from app.modules.bi.services.operacoes import (
    _apply_filters,
    _as_float,
    _build_provenance,
    _produto_expr,
    _receita_total_expr,
    _weighted_avg,
)
from app.shared.audit_log.sync_health import last_data_update_at
from app.warehouse.operacao import Operacao
from app.warehouse.titulo import Titulo


def _receita_row_expr() -> Any:
    """Receita de UMA operacao (row-level, sem agregacao). Soma dos 4 buckets
    regime caixa — espelha `_receita_total_expr` (que e a versao agregada)."""
    return (
        Operacao.total_de_juros
        + Operacao.total_dos_comunicados_de_cessao
        + Operacao.total_das_consultas_financeiras
        + Operacao.total_das_consultas_fiscais
        + Operacao.total_dos_registros_bancarios
        + Operacao.total_dos_documentos_digitais
        + Operacao.total_de_ad_valorem
        + Operacao.total_de_rebate
    )


async def get_cedentes_ranking(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[Operacoes5CedentesData, Provenance]:
    """Ranking de cedentes no periodo filtrado (nivel Cedente da espinha).

    Agrupa wh_operacao por cedente_id; VOP, receita, taxa/prazo wavg. Retorna
    TODOS os cedentes (sem corte) ordenados por VOP desc — reconcilia com o
    VOP total da pagina. Toda query passa por `_apply_filters` (§7.2).
    """
    vop_agg = func.coalesce(func.sum(Operacao.total_bruto), 0)
    stmt = select(
        Operacao.cedente_id,
        func.max(Operacao.cedente_nome).label("nome"),
        func.max(Operacao.cedente_documento).label("doc"),
        vop_agg.label("vop"),
        func.count(Operacao.id).label("n_op"),
        _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("taxa"),
        _weighted_avg(Operacao.prazo_medio_real, Operacao.total_bruto).label("prazo"),
        _receita_total_expr().label("receita"),
    )
    stmt = _apply_filters(stmt, tenant_id=tenant_id, **filters)
    stmt = stmt.group_by(Operacao.cedente_id).order_by(vop_agg.desc())
    rows = (await db.execute(stmt)).all()

    vop_total = sum(_as_float(r.vop) for r in rows)
    receita_total = sum(_as_float(r.receita) for r in rows)

    cedentes = [
        Operacoes5CedenteItem(
            cedente_id=r.cedente_id,
            cedente_nome=r.nome or "(n/d)",
            cedente_documento=r.doc,
            vop=_as_float(r.vop),
            n_op=int(r.n_op or 0),
            taxa_media=(_as_float(r.taxa) if r.taxa is not None else None),
            prazo_medio=(_as_float(r.prazo) if r.prazo is not None else None),
            receita=_as_float(r.receita),
            yield_pct=(
                _as_float(r.receita) / _as_float(r.vop) * 100.0
                if _as_float(r.vop) > 0
                else None
            ),
            share_pct=(_as_float(r.vop) / vop_total * 100.0) if vop_total > 0 else 0.0,
        )
        for r in rows
    ]

    prov = await _build_provenance(db, tenant_id, filters)
    data = Operacoes5CedentesData(
        cedentes=cedentes,
        total=len(cedentes),
        vop_total=vop_total,
        receita_total=receita_total,
    )
    return data, prov


async def get_operacoes_por_cedente(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[Operacoes5OperacoesData, Provenance]:
    """Operacoes de um cedente no periodo (nivel Operacao = drawer).

    `filters["cedente_id"]` selecione o cedente (aplicado via `_apply_filters`).
    1 linha por operacao (wh_operacao e 1 row/op). Reconcilia: sum(vop) ==
    vop_total. Demais filtros globais (UA, produto, periodo) continuam valendo.
    """
    receita_row = _receita_row_expr()
    data_expr = cast(Operacao.data_de_efetivacao, Date)
    stmt = select(
        Operacao.operacao_id,
        data_expr.label("data"),
        _produto_expr().label("produto"),
        Operacao.modalidade,
        Operacao.quantidade_de_titulos,
        Operacao.total_bruto,
        Operacao.total_liquido,
        Operacao.taxa_de_juros,
        Operacao.prazo_medio_real,
        Operacao.cedente_id,
        Operacao.cedente_nome,
        Operacao.cedente_documento,
        receita_row.label("receita"),
        # Composicao da receita (regime caixa) — abrir cada tarifa.
        Operacao.total_de_juros,
        Operacao.total_dos_comunicados_de_cessao,
        Operacao.total_das_consultas_financeiras,
        Operacao.total_das_consultas_fiscais,
        Operacao.total_dos_registros_bancarios,
        Operacao.total_dos_documentos_digitais,
        Operacao.total_de_ad_valorem,
        Operacao.total_de_rebate,
        # Tributos / ajustes — nao-receita.
        Operacao.total_de_iof,
        Operacao.total_de_imposto,
        Operacao.total_dos_descontos_ou_abatimentos,
    )
    stmt = _apply_filters(stmt, tenant_id=tenant_id, **filters)
    stmt = stmt.order_by(data_expr.desc(), Operacao.operacao_id.desc())
    rows = (await db.execute(stmt)).all()

    operacoes = [
        Operacoes5OperacaoItem(
            operacao_id=r.operacao_id,
            data_de_efetivacao=r.data,
            produto=r.produto or "(n/d)",
            modalidade=r.modalidade,
            quantidade_de_titulos=int(r.quantidade_de_titulos or 0),
            vop=_as_float(r.total_bruto),
            total_liquido=_as_float(r.total_liquido),
            taxa_juros=_as_float(r.taxa_de_juros),
            prazo_medio=_as_float(r.prazo_medio_real),
            receita=_as_float(r.receita),
            rec_desagio=_as_float(r.total_de_juros),
            rec_tarifa_cessao=_as_float(r.total_dos_comunicados_de_cessao),
            rec_consultas_financeiras=_as_float(r.total_das_consultas_financeiras),
            rec_consultas_fiscais=_as_float(r.total_das_consultas_fiscais),
            rec_registros_bancarios=_as_float(r.total_dos_registros_bancarios),
            rec_documentos_digitais=_as_float(r.total_dos_documentos_digitais),
            rec_ad_valorem=_as_float(r.total_de_ad_valorem),
            rec_rebate=_as_float(r.total_de_rebate),
            trib_iof=_as_float(r.total_de_iof),
            trib_imposto=_as_float(r.total_de_imposto),
            trib_descontos=_as_float(r.total_dos_descontos_ou_abatimentos),
        )
        for r in rows
    ]

    vop_total = sum(o.vop for o in operacoes)
    receita_total = sum(o.receita for o in operacoes)
    cedente_id = filters.get("cedente_id")
    cedente_nome = rows[0].cedente_nome if rows else "(n/d)"
    cedente_documento = rows[0].cedente_documento if rows else None

    prov = await _build_provenance(db, tenant_id, filters)
    data = Operacoes5OperacoesData(
        cedente_id=cedente_id,
        cedente_nome=cedente_nome or "(n/d)",
        cedente_documento=cedente_documento,
        operacoes=operacoes,
        total=len(operacoes),
        vop_total=vop_total,
        receita_total=receita_total,
    )
    return data, prov


async def get_documentos_por_operacao(
    db: AsyncSession, tenant_id: UUID, operacao_id: int
) -> tuple[Operacoes5DocumentosData, Provenance]:
    """Documentos (titulos) de uma operacao (nivel Documento = inline).

    Decomposicao completa da operacao: TODOS os titulos (wh_titulo) daquela
    operacao, escopados por tenant. Sem corte por periodo — os titulos sao a
    explicacao integral da operacao, reconciliam com o valor dela (§14.6).
    """
    stmt = (
        select(Titulo)
        .where(Titulo.tenant_id == tenant_id, Titulo.operacao_id == operacao_id)
        .order_by(Titulo.data_de_vencimento_efetiva.asc(), Titulo.titulo_id.asc())
    )
    rows = list((await db.execute(stmt)).scalars().all())

    documentos = [
        Operacoes5DocumentoItem(
            titulo_id=t.titulo_id,
            sigla=t.sigla,
            numero=t.numero,
            sacado_id=t.sacado_id,
            valor=_as_float(t.valor),
            valor_liquido=_as_float(t.valor_liquido),
            saldo_devedor=_as_float(t.saldo_devedor),
            data_de_vencimento_efetiva=(
                t.data_de_vencimento_efetiva.date()
                if t.data_de_vencimento_efetiva
                else None
            ),
            situacao=t.situacao,
            status=t.status,
        )
        for t in rows
    ]
    valor_total = sum(d.valor for d in documentos)

    last_source_updated = max((t.source_updated_at for t in rows), default=None)
    prov = Provenance(
        source_type="erp:bitfin",
        source_ids=["wh_titulo"],
        last_sync_at=await last_data_update_at(db, tenant_id, Titulo),
        last_source_updated_at=last_source_updated,
        trust_level="high",
        ingested_by_version="bitfin_adapter_v1.0.0",
        row_count=len(rows),
    )
    data = Operacoes5DocumentosData(
        operacao_id=operacao_id,
        documentos=documentos,
        total=len(documentos),
        valor_total=valor_total,
    )
    return data, prov
