"""L2 Operacoes2 — service da nova UX (refatoracao 2026-05-03).

Reutiliza as funcoes utilitarias de `services/operacoes.py` (`_apply_filters`,
`_weighted_avg`, `_shift_period_back`, etc) — este modulo so monta os bundles
novos (KPI Strip + Aba 1).

Decisao 2026-05-03 (Opcao 4 do paradigma de periodos):
- KPI Strip carrega valor do PERIODO + valor do MES CORRENTE em cada cell.
- Quebras (`por_ua`, `por_produto`) carregam vop/pct do periodo + do mes
  corrente — frontend toggla "Periodo | Mes | Ambos" no card.
- Hero Evolucao 12M expoe serie segmentada por UA (`evolucao_12m_por_ua`)
  alem da agregada — frontend usa pra filtrar 1 UA local sem ida extra ao
  backend.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Date,
    Numeric,
    String,
    and_,
    cast,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bi.schemas.common import Point, Provenance
from app.modules.bi.schemas.operacoes2 import (
    AbaVolumeRitmoData,
    AcumuladoDiarioPonto,
    DiaSemanaResumo,
    EvolucaoMensalPonto,
    EvolucaoPorUaPonto,
    HeatmapDowSemanaPonto,
    KpiCellNumeric,
    KpiCellProduto,
    KpiSecundario,
    KpisSecundariosVolume,
    MesCorrenteVsMedia,
    MesDestaque,
    OperacoesKpiStripData,
    PaceDiario,
    QuebraDimensaoLinha,
    RitmoMesCorrente,
)
from app.modules.bi.services.operacoes import (
    _apply_filters,
    _as_float,
    _build_provenance,
    _fmt_comparacao_label_pt,
    _produto_expr,
    _produto_sigla_to_nome_map,
    _safe_pct_change,
    _scalar_count_ops,
    _scalar_sum_titulos,
    _scalar_sum_volume,
    _shift_period_back,
    _ua_id_to_nome_map,
    _weighted_avg,
)
from app.warehouse.dim_dia_util import DimDiaUtil
from app.warehouse.operacao import Operacao


# ═══════════════════════════════════════════════════════════════════════════
# Helpers especificos do operacoes2
# ═══════════════════════════════════════════════════════════════════════════


_MES_PT_LONGO = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)


def _mes_corrente_window(periodo_fim: date | None) -> tuple[date, date, str]:
    """Janela do mes corrente: (1o dia do mes, fim, label 'Mes/Ano')."""
    end = periodo_fim or date.today()
    start = end.replace(day=1)
    label = f"{_MES_PT_LONGO[end.month - 1]}/{end.year}"
    return start, end, label


def _sparkline_12m_window(periodo_fim: date | None) -> tuple[date, date]:
    """Calcula a janela 12M (1o dia do mes 11 meses atras → mes corrente)."""
    end = periodo_fim or date.today()
    end_first = end.replace(day=1)
    y, m = end_first.year, end_first.month - 11
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1), end


def _mm_3m(values: list[float]) -> list[float | None]:
    """Media movel de 3 meses. Indices 0/1 retornam None."""
    out: list[float | None] = []
    for i, _ in enumerate(values):
        if i < 2:
            out.append(None)
        else:
            out.append(sum(values[i - 2 : i + 1]) / 3.0)
    return out


async def _has_dim_dia_util(db: AsyncSession, tenant_id: UUID) -> bool:
    """Retorna True se `wh_dim_dia_util` tem pelo menos uma linha do tenant."""
    stmt = select(func.count(DimDiaUtil.id)).where(DimDiaUtil.tenant_id == tenant_id)
    n = (await db.execute(stmt)).scalar_one()
    return int(n or 0) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Endpoint 1 — KPI Strip (5 indicadores-chave + sparklines + mes corrente)
# ═══════════════════════════════════════════════════════════════════════════


async def get_kpi_strip(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[OperacoesKpiStripData, Provenance]:
    """Bundle dos 5 KPIs com Periodo + Mes Corrente para Strip Dual."""
    periodo_inicio: date | None = filters.get("periodo_inicio")
    periodo_fim: date | None = filters.get("periodo_fim")

    # ── Agregados do PERIODO ──────────────────────────────────────────────
    agg_periodo = await _agg_kpi(db, tenant_id, filters)

    # ── Agregados do MES CORRENTE (mesmo filtros, periodo override) ───────
    mes_inicio, mes_fim, mes_label = _mes_corrente_window(periodo_fim)
    mes_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": mes_fim}
    agg_mes = await _agg_kpi(db, tenant_id, mes_filters)

    # ── Periodo anterior (mesmo tamanho): para deltas do PERIODO ──────────
    prev_inicio, prev_fim = _shift_period_back(periodo_inicio, periodo_fim)
    agg_anterior: dict[str, float | None] = {
        "vop": None,
        "receita": None,
        "taxa": None,
        "prazo": None,
    }
    if prev_inicio and prev_fim:
        prev_filters = {**filters, "periodo_inicio": prev_inicio, "periodo_fim": prev_fim}
        agg_anterior = await _agg_kpi(db, tenant_id, prev_filters)

    # ── Sparklines 12M ─────────────────────────────────────────────────────
    sparklines = await _sparklines_12m(db, tenant_id, filters, periodo_fim)

    # ── Produto top (periodo) ─────────────────────────────────────────────
    prod_top_periodo = await _produto_top_share(
        db, tenant_id, filters, agg_periodo["vop"]
    )

    # ── Produto top (mes corrente) ────────────────────────────────────────
    prod_top_mes = await _produto_top_share(db, tenant_id, mes_filters, agg_mes["vop"])

    # ── Delta_pp do produto top do periodo (vs periodo anterior) ─────────
    produto_top_delta_pp: float | None = None
    if prod_top_periodo["sigla"] != "—" and prev_inicio and prev_fim:
        prev_filters = {**filters, "periodo_inicio": prev_inicio, "periodo_fim": prev_fim}
        prev_p_stmt = _apply_filters(
            select(
                _produto_expr().label("sigla"),
                func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
            ).group_by(_produto_expr()),
            tenant_id=tenant_id,
            **prev_filters,
        )
        prev_p = {
            str(r.sigla or ""): _as_float(r.valor)
            for r in (await db.execute(prev_p_stmt)).all()
        }
        prev_total = sum(prev_p.values())
        if prev_total > 0 and prod_top_periodo["sigla"] in prev_p:
            prev_share = prev_p[prod_top_periodo["sigla"]] / prev_total * 100
            produto_top_delta_pp = prod_top_periodo["share_pct"] - prev_share

    # ── Lookup nomes de produto ───────────────────────────────────────────
    prod_nomes = await _produto_sigla_to_nome_map(db, tenant_id)

    # ── Bundle final ──────────────────────────────────────────────────────
    label_cmp = _fmt_comparacao_label_pt(prev_inicio, prev_fim)

    data = OperacoesKpiStripData(
        vop=KpiCellNumeric(
            valor=agg_periodo["vop"],
            unidade="BRL",
            delta_pct=_safe_pct_change(agg_periodo["vop"], agg_anterior["vop"])
            if agg_anterior["vop"] is not None
            else None,
            sparkline_12m=sparklines["vop"],
            mes_corrente_valor=agg_mes["vop"],
            mes_corrente_label=mes_label,
        ),
        taxa_media=KpiCellNumeric(
            valor=agg_periodo["taxa"],
            unidade="%",
            delta_pct=_safe_pct_change(agg_periodo["taxa"], agg_anterior["taxa"])
            if (agg_anterior["taxa"] is not None and agg_anterior["taxa"] > 0)
            else None,
            sparkline_12m=sparklines["taxa"],
            mes_corrente_valor=agg_mes["taxa"],
            mes_corrente_label=mes_label,
        ),
        prazo_medio=KpiCellNumeric(
            valor=agg_periodo["prazo"],
            unidade="dias",
            delta_pct=_safe_pct_change(agg_periodo["prazo"], agg_anterior["prazo"])
            if (agg_anterior["prazo"] is not None and agg_anterior["prazo"] > 0)
            else None,
            sparkline_12m=sparklines["prazo"],
            mes_corrente_valor=agg_mes["prazo"],
            mes_corrente_label=mes_label,
        ),
        produto_top=KpiCellProduto(
            sigla=prod_top_periodo["sigla"],
            nome=prod_nomes.get(prod_top_periodo["sigla"]),
            share_pct=prod_top_periodo["share_pct"],
            delta_share_pp=produto_top_delta_pp,
            sparkline_share_12m=sparklines["produto_top"],
            mes_corrente_sigla=prod_top_mes["sigla"],
            mes_corrente_nome=prod_nomes.get(prod_top_mes["sigla"]),
            mes_corrente_share_pct=prod_top_mes["share_pct"],
            mes_corrente_label=mes_label,
        ),
        receita_contratada=KpiCellNumeric(
            valor=agg_periodo["receita"],
            unidade="BRL",
            delta_pct=_safe_pct_change(agg_periodo["receita"], agg_anterior["receita"])
            if agg_anterior["receita"] is not None
            else None,
            sparkline_12m=sparklines["receita"],
            mes_corrente_valor=agg_mes["receita"],
            mes_corrente_label=mes_label,
        ),
        comparacao_label_pt=label_cmp,
    )
    prov = await _build_provenance(db, tenant_id, filters)
    return data, prov


async def _agg_kpi(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> dict[str, float]:
    """Agregados consolidados (vop, receita, taxa, prazo) com filtros aplicados."""
    stmt = _apply_filters(
        select(
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
            func.coalesce(func.sum(Operacao.total_de_juros), 0).label("juros"),
            func.coalesce(func.sum(Operacao.total_das_consultas_financeiras), 0).label("cf"),
            func.coalesce(func.sum(Operacao.total_dos_registros_bancarios), 0).label("rb"),
            func.coalesce(func.sum(Operacao.total_das_consultas_fiscais), 0).label("cfi"),
            func.coalesce(func.sum(Operacao.total_dos_comunicados_de_cessao), 0).label("cc"),
            func.coalesce(func.sum(Operacao.total_dos_documentos_digitais), 0).label("dd"),
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("taxa"),
            _weighted_avg(Operacao.prazo_medio_real, Operacao.total_bruto).label("prazo"),
        ),
        tenant_id=tenant_id,
        **filters,
    )
    row = (await db.execute(stmt)).one()
    return {
        "vop": _as_float(row.vop),
        "receita": _as_float(
            (row.juros or 0)
            + (row.cf or 0)
            + (row.rb or 0)
            + (row.cfi or 0)
            + (row.cc or 0)
            + (row.dd or 0)
        ),
        "taxa": _as_float(row.taxa) if row.taxa is not None else 0.0,
        "prazo": _as_float(row.prazo) if row.prazo is not None else 0.0,
    }


async def _produto_top_share(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    vop_total: float,
) -> dict[str, Any]:
    """Retorna `{sigla, share_pct}` do produto com maior volume nos filtros."""
    stmt = _apply_filters(
        select(
            _produto_expr().label("sigla"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
        )
        .group_by(_produto_expr())
        .order_by(func.sum(Operacao.total_bruto).desc())
        .limit(1),
        tenant_id=tenant_id,
        **filters,
    )
    row = (await db.execute(stmt)).first()
    if row is None or row.sigla is None or vop_total <= 0:
        return {"sigla": "—", "share_pct": 0.0}
    return {
        "sigla": str(row.sigla),
        "share_pct": _as_float(row.valor) / vop_total * 100,
    }


async def _sparklines_12m(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    periodo_fim: date | None,
) -> dict[str, list[Point]]:
    """Sparklines 12M para vop, receita, taxa, prazo, produto_top (share)."""
    spark_start, spark_end = _sparkline_12m_window(periodo_fim)
    spark_filters = {**filters, "periodo_inicio": spark_start, "periodo_fim": spark_end}
    bucket = func.date_trunc("month", Operacao.data_de_efetivacao)

    spark_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
            (
                func.coalesce(func.sum(Operacao.total_de_juros), 0)
                + func.coalesce(func.sum(Operacao.total_das_consultas_financeiras), 0)
                + func.coalesce(func.sum(Operacao.total_dos_registros_bancarios), 0)
                + func.coalesce(func.sum(Operacao.total_das_consultas_fiscais), 0)
                + func.coalesce(func.sum(Operacao.total_dos_comunicados_de_cessao), 0)
                + func.coalesce(func.sum(Operacao.total_dos_documentos_digitais), 0)
            ).label("receita"),
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("taxa"),
            _weighted_avg(Operacao.prazo_medio_real, Operacao.total_bruto).label("prazo"),
        )
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **spark_filters,
    )
    rows = (await db.execute(spark_stmt)).all()
    spark_vop = [Point(periodo=r.periodo, valor=_as_float(r.vop)) for r in rows]
    spark_receita = [Point(periodo=r.periodo, valor=_as_float(r.receita)) for r in rows]
    spark_taxa = [
        Point(periodo=r.periodo, valor=_as_float(r.taxa) if r.taxa is not None else 0.0)
        for r in rows
    ]
    spark_prazo = [
        Point(periodo=r.periodo, valor=_as_float(r.prazo) if r.prazo is not None else 0.0)
        for r in rows
    ]

    # Sparkline do share do produto top (do periodo) — % mes a mes
    prod_top_periodo = await _produto_top_share(
        db, tenant_id, filters, sum(p.valor for p in spark_vop) or 1.0
    )
    spark_produto_top: list[Point] = []
    if prod_top_periodo["sigla"] != "—":
        spark_p_stmt = _apply_filters(
            select(
                cast(bucket, Date).label("periodo"),
                _produto_expr().label("sigla"),
                func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
            )
            .group_by(bucket, _produto_expr())
            .order_by(bucket),
            tenant_id=tenant_id,
            **spark_filters,
        )
        spark_p_rows = (await db.execute(spark_p_stmt)).all()
        totals_by_month: dict[date, float] = {}
        lider_by_month: dict[date, float] = {}
        for r in spark_p_rows:
            v = _as_float(r.valor)
            totals_by_month[r.periodo] = totals_by_month.get(r.periodo, 0.0) + v
            if str(r.sigla or "") == prod_top_periodo["sigla"]:
                lider_by_month[r.periodo] = v
        spark_produto_top = [
            Point(
                periodo=p,
                valor=(lider_by_month.get(p, 0.0) / totals_by_month[p] * 100)
                if totals_by_month.get(p, 0.0) > 0
                else 0.0,
            )
            for p in sorted(totals_by_month.keys())
        ]
    return {
        "vop": spark_vop,
        "receita": spark_receita,
        "taxa": spark_taxa,
        "prazo": spark_prazo,
        "produto_top": spark_produto_top,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Endpoint 2 — Aba 1: Volume & Ritmo
# ═══════════════════════════════════════════════════════════════════════════


async def get_aba1_volume_ritmo(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[AbaVolumeRitmoData, Provenance]:
    """Bundle completo da Aba 1 — Volume & Ritmo (com mes_corrente em quebras)."""
    periodo_inicio: date | None = filters.get("periodo_inicio")
    periodo_fim: date | None = filters.get("periodo_fim")
    bucket = func.date_trunc("month", Operacao.data_de_efetivacao)

    # Janela mes corrente (para quebras dual)
    mes_inicio, mes_fim, _mes_label = _mes_corrente_window(periodo_fim)
    mes_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": mes_fim}

    # ── Linha 1: Evolucao mensal (respeita o filtro de periodo do header) ──
    # Usa `filters` (do user) — quando user seleciona "3 meses" no chip de
    # periodo do header, o chart mostra 3 meses; "12 meses" mostra 12; etc.
    # Sparklines do KPI Strip continuam 12M FIXOS (visao historica do KPI),
    # mas o Hero da Aba 1 reflete o filtro como esperado.
    evo_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
            func.count(Operacao.id).label("n"),
        )
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **filters,
    )
    evo_rows = (await db.execute(evo_stmt)).all()
    vops = [_as_float(r.vop) for r in evo_rows]
    mm3 = _mm_3m(vops)
    evolucao_12m: list[EvolucaoMensalPonto] = []
    for r, mm in zip(evo_rows, mm3, strict=True):
        n = int(r.n or 0)
        v = _as_float(r.vop)
        evolucao_12m.append(
            EvolucaoMensalPonto(
                periodo=r.periodo.isoformat() if isinstance(r.periodo, date) else str(r.periodo),
                vop=v,
                n_operacoes=n,
                ticket_medio=(v / n) if n > 0 else 0.0,
                mm_3m=mm,
            )
        )

    # Serie segmentada por UA — mesma janela do filtro (`filters`) para que
    # quando o user trocar pra "3 meses" no header, ambos os modos do hero
    # (Todas / UA especifica) refletem 3 meses.
    ua_nomes = await _ua_id_to_nome_map(db, tenant_id)
    evo_ua_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            Operacao.unidade_administrativa_id.label("ua_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
        )
        .group_by(bucket, Operacao.unidade_administrativa_id)
        .order_by(bucket, Operacao.unidade_administrativa_id),
        tenant_id=tenant_id,
        **filters,
    )
    evo_ua_rows = (await db.execute(evo_ua_stmt)).all()
    evolucao_12m_por_ua: list[EvolucaoPorUaPonto] = [
        EvolucaoPorUaPonto(
            periodo=r.periodo.isoformat() if isinstance(r.periodo, date) else str(r.periodo),
            ua_id=int(r.ua_id),
            ua_nome=ua_nomes.get(int(r.ua_id), f"UA {int(r.ua_id)}"),
            vop=_as_float(r.vop),
        )
        for r in evo_ua_rows
        if r.ua_id is not None
    ]

    # Mini-stats: melhor / pior mes / corrente vs media
    melhor_mes: MesDestaque | None = None
    pior_mes: MesDestaque | None = None
    mes_vs_media: MesCorrenteVsMedia | None = None
    if evolucao_12m:
        sorted_by_vop = sorted(evolucao_12m, key=lambda p: p.vop)
        pior_mes = MesDestaque(periodo=sorted_by_vop[0].periodo, vop=sorted_by_vop[0].vop)
        melhor_mes = MesDestaque(periodo=sorted_by_vop[-1].periodo, vop=sorted_by_vop[-1].vop)
        media_12m = sum(vops) / len(vops) if vops else 0.0
        corrente = evolucao_12m[-1]
        mes_vs_media = MesCorrenteVsMedia(
            vop_corrente=corrente.vop,
            media_12m=media_12m,
            pct=(corrente.vop / media_12m - 1) * 100 if media_12m > 0 else 0.0,
        )

    # ── Linha 2: Ritmo do mes corrente (degraded mode quando DU vazio) ─────
    has_du = await _has_dim_dia_util(db, tenant_id)
    ritmo: RitmoMesCorrente | None = None
    pace: PaceDiario | None = None
    if has_du:
        ritmo, pace = await _calc_ritmo_e_pace(db, tenant_id, filters)

    # ── Linha 3: KPIs secundarios ──────────────────────────────────────────
    n_ops_atual = await _scalar_count_ops(db, tenant_id, filters, periodo_inicio, periodo_fim)
    vol_atual = await _scalar_sum_volume(db, tenant_id, filters, periodo_inicio, periodo_fim)
    tit_atual = await _scalar_sum_titulos(db, tenant_id, filters, periodo_inicio, periodo_fim)
    ticket_op_atual = (vol_atual / n_ops_atual) if n_ops_atual > 0 else 0.0
    ticket_titulo_atual = (vol_atual / tit_atual) if tit_atual > 0 else 0.0

    prev_inicio, prev_fim = _shift_period_back(periodo_inicio, periodo_fim)
    n_ops_prev = vol_prev = tit_prev = 0
    if prev_inicio and prev_fim:
        n_ops_prev = await _scalar_count_ops(db, tenant_id, filters, prev_inicio, prev_fim)
        vol_prev = await _scalar_sum_volume(db, tenant_id, filters, prev_inicio, prev_fim)
        tit_prev = await _scalar_sum_titulos(db, tenant_id, filters, prev_inicio, prev_fim)

    ticket_op_prev = (vol_prev / n_ops_prev) if n_ops_prev > 0 else None
    ticket_titulo_prev = (vol_prev / tit_prev) if tit_prev > 0 else None

    vop_du_medio_kpi: KpiSecundario | None = None
    if has_du and ritmo is not None and pace is not None:
        vop_du_medio_kpi = KpiSecundario(
            valor=pace.vop_du_corrente,
            delta_pct=pace.delta_pct,
        )

    kpis_secundarios = KpisSecundariosVolume(
        n_operacoes=KpiSecundario(
            valor=float(n_ops_atual),
            delta_pct=_safe_pct_change(float(n_ops_atual), float(n_ops_prev))
            if n_ops_prev > 0
            else None,
        ),
        ticket_op=KpiSecundario(
            valor=ticket_op_atual,
            delta_pct=_safe_pct_change(ticket_op_atual, ticket_op_prev)
            if ticket_op_prev is not None
            else None,
        ),
        ticket_titulo=KpiSecundario(
            valor=ticket_titulo_atual,
            delta_pct=_safe_pct_change(ticket_titulo_atual, ticket_titulo_prev)
            if ticket_titulo_prev is not None
            else None,
        ),
        vop_du_medio=vop_du_medio_kpi,
    )

    # ── Linha 1 (UA) + Linha 4 (Produto) — quebras com mes corrente ───────
    vop_mes = await _scalar_sum_volume(db, tenant_id, mes_filters, mes_inicio, mes_fim)
    por_ua = await _quebra_dimensao(
        db,
        tenant_id,
        filters,
        mes_filters,
        "ua",
        vol_atual,
        vop_mes,
        periodo_inicio,
        periodo_fim,
    )
    por_produto = await _quebra_dimensao(
        db,
        tenant_id,
        filters,
        mes_filters,
        "produto",
        vol_atual,
        vop_mes,
        periodo_inicio,
        periodo_fim,
    )

    # ── Linha 5: heatmap + por dia da semana ──────────────────────────────
    heatmap_rows = await _heatmap_dow_semana(db, tenant_id, filters)
    dia_semana_rows = await _por_dia_semana(db, tenant_id, filters)

    data = AbaVolumeRitmoData(
        evolucao_12m=evolucao_12m,
        evolucao_12m_por_ua=evolucao_12m_por_ua,
        melhor_mes=melhor_mes,
        pior_mes=pior_mes,
        mes_corrente_vs_media=mes_vs_media,
        ritmo=ritmo,
        pace_diario=pace,
        kpis_secundarios=kpis_secundarios,
        por_ua=por_ua,
        por_produto=por_produto,
        heatmap_dow_semana=heatmap_rows,
        por_dia_semana=dia_semana_rows,
    )
    prov = await _build_provenance(db, tenant_id, filters)
    return data, prov


# ═══════════════════════════════════════════════════════════════════════════
# Helpers de quebra / heatmap / ritmo
# ═══════════════════════════════════════════════════════════════════════════


async def _quebra_dimensao(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    mes_filters: dict[str, Any],
    dim: str,
    vol_atual_total: float,
    vol_mes_total: float,
    periodo_inicio: date | None,
    periodo_fim: date | None,
) -> list[QuebraDimensaoLinha]:
    """Quebra por dimensao (UA ou Produto) com share + MoM + YoY + mes corrente.

    `dim` aceita 'ua' ou 'produto'. Top 10 do periodo retornado.
    """
    if dim == "ua":
        cat_expr: ColumnElement[Any] = Operacao.unidade_administrativa_id
        nomes_map = await _ua_id_to_nome_map(db, tenant_id)
        cat_to_label = lambda cid: nomes_map.get(int(cid), f"UA {int(cid)}") if cid is not None else "(n/d)"
        cat_to_id_str = lambda cid: str(int(cid)) if cid is not None else "0"
    elif dim == "produto":
        cat_expr = _produto_expr()
        prod_nomes = await _produto_sigla_to_nome_map(db, tenant_id)
        # Label exibe o nome completo (Faturizacao, Comissaria...) com fallback pra sigla.
        cat_to_label = lambda cid: prod_nomes.get(str(cid), str(cid) if cid else "(n/d)")
        cat_to_id_str = lambda cid: str(cid) if cid else "(n/d)"
    else:
        raise ValueError(f"Dimensao desconhecida: {dim}")

    # ── Periodo (atual) ────────────────────────────────────────────────────
    stmt_periodo = _apply_filters(
        select(
            cat_expr.label("categoria_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
        )
        .group_by(cat_expr)
        .order_by(func.sum(Operacao.total_bruto).desc()),
        tenant_id=tenant_id,
        **filters,
    )
    rows_periodo = (await db.execute(stmt_periodo)).all()

    # ── Mes corrente — agregado por mesma categoria ───────────────────────
    stmt_mes = _apply_filters(
        select(
            cat_expr.label("categoria_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
        ).group_by(cat_expr),
        tenant_id=tenant_id,
        **mes_filters,
    )
    mes_map = {
        cat_to_id_str(r.categoria_id): _as_float(r.valor)
        for r in (await db.execute(stmt_mes)).all()
    }

    # ── Periodo anterior (MoM) ────────────────────────────────────────────
    prev_mom_inicio, prev_mom_fim = _shift_period_back(periodo_inicio, periodo_fim)
    prev_mom_map: dict[str, float] = {}
    if prev_mom_inicio and prev_mom_fim:
        prev_filters = {**filters, "periodo_inicio": prev_mom_inicio, "periodo_fim": prev_mom_fim}
        prev_stmt = _apply_filters(
            select(
                cat_expr.label("categoria_id"),
                func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
            ).group_by(cat_expr),
            tenant_id=tenant_id,
            **prev_filters,
        )
        prev_mom_map = {
            cat_to_id_str(r.categoria_id): _as_float(r.valor)
            for r in (await db.execute(prev_stmt)).all()
        }

    # ── YoY: mesmo periodo 12 meses antes ─────────────────────────────────
    prev_yoy_map: dict[str, float] = {}
    if periodo_inicio and periodo_fim:
        try:
            yoy_inicio = periodo_inicio.replace(year=periodo_inicio.year - 1)
        except ValueError:
            yoy_inicio = periodo_inicio.replace(year=periodo_inicio.year - 1, day=28)
        try:
            yoy_fim = periodo_fim.replace(year=periodo_fim.year - 1)
        except ValueError:
            yoy_fim = periodo_fim.replace(year=periodo_fim.year - 1, day=28)
        yoy_filters = {**filters, "periodo_inicio": yoy_inicio, "periodo_fim": yoy_fim}
        yoy_stmt = _apply_filters(
            select(
                cat_expr.label("categoria_id"),
                func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
            ).group_by(cat_expr),
            tenant_id=tenant_id,
            **yoy_filters,
        )
        prev_yoy_map = {
            cat_to_id_str(r.categoria_id): _as_float(r.valor)
            for r in (await db.execute(yoy_stmt)).all()
        }

    out: list[QuebraDimensaoLinha] = []
    for r in rows_periodo:
        cid_str = cat_to_id_str(r.categoria_id)
        valor = _as_float(r.valor)
        mes_v = mes_map.get(cid_str, 0.0)
        out.append(
            QuebraDimensaoLinha(
                categoria_id=cid_str,
                categoria=cat_to_label(r.categoria_id),
                vop=valor,
                pct=(valor / vol_atual_total * 100) if vol_atual_total > 0 else 0.0,
                delta_mom_pct=_safe_pct_change(valor, prev_mom_map.get(cid_str, 0.0))
                if prev_mom_map.get(cid_str, 0.0) > 0
                else None,
                delta_yoy_pct=_safe_pct_change(valor, prev_yoy_map.get(cid_str, 0.0))
                if prev_yoy_map.get(cid_str, 0.0) > 0
                else None,
                vop_mes_corrente=mes_v,
                pct_mes_corrente=(mes_v / vol_mes_total * 100)
                if vol_mes_total > 0
                else 0.0,
            )
        )
    return out


async def _heatmap_dow_semana(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> list[HeatmapDowSemanaPonto]:
    """Heatmap dow x semana do mes — VOP medio por celula no periodo."""
    dow = func.extract("isodow", Operacao.data_de_efetivacao)
    semana = func.cast(func.ceil(func.extract("day", Operacao.data_de_efetivacao) / 7.0), Numeric)

    stmt = _apply_filters(
        select(
            dow.label("dow"),
            semana.label("semana"),
            func.avg(Operacao.total_bruto).label("vop_medio"),
            func.count(Operacao.id).label("n"),
        )
        .group_by(dow, semana)
        .order_by(dow, semana),
        tenant_id=tenant_id,
        **filters,
    )
    rows = (await db.execute(stmt)).all()
    out: list[HeatmapDowSemanaPonto] = []
    for r in rows:
        if r.dow is None or r.semana is None:
            continue
        d = int(r.dow)
        if d > 5:
            continue
        s = int(r.semana)
        if s < 1 or s > 5:
            continue
        out.append(
            HeatmapDowSemanaPonto(
                dow=d,
                semana_do_mes=s,
                vop_medio=_as_float(r.vop_medio),
                n_ops=int(r.n or 0),
            )
        )
    return out


_DOW_LABELS_PT = {
    1: "Segunda",
    2: "Terça",
    3: "Quarta",
    4: "Quinta",
    5: "Sexta",
    6: "Sábado",
    7: "Domingo",
}


async def _por_dia_semana(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> list[DiaSemanaResumo]:
    """VOP medio por dia da semana (segunda-sexta) + share da semana util."""
    dow = func.extract("isodow", Operacao.data_de_efetivacao)
    stmt = _apply_filters(
        select(
            dow.label("dow"),
            func.avg(Operacao.total_bruto).label("vop_medio"),
            func.avg(Operacao.quantidade_de_titulos).label("n_ops_medio"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop_total"),
        )
        .group_by(dow)
        .order_by(dow),
        tenant_id=tenant_id,
        **filters,
    )
    rows = (await db.execute(stmt)).all()

    rows_uteis = [r for r in rows if r.dow is not None and 1 <= int(r.dow) <= 5]
    total_semana_util = sum(_as_float(r.vop_total) for r in rows_uteis) or 1.0

    out: list[DiaSemanaResumo] = []
    for r in rows_uteis:
        d = int(r.dow)
        out.append(
            DiaSemanaResumo(
                dow=d,
                nome=_DOW_LABELS_PT.get(d, "(n/d)"),
                vop_medio=_as_float(r.vop_medio),
                n_ops_medio=_as_float(r.n_ops_medio),
                pct_total_semana=_as_float(r.vop_total) / total_semana_util * 100,
            )
        )
    return out


async def _calc_ritmo_e_pace(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[RitmoMesCorrente | None, PaceDiario | None]:
    """Calcula ritmo do mes corrente + pace diario (depende wh_dim_dia_util)."""
    periodo_fim: date | None = filters.get("periodo_fim")
    hoje = periodo_fim or date.today()

    mes_inicio = hoje.replace(day=1)
    if hoje.month == 1:
        mes_anterior_inicio = date(hoje.year - 1, 12, 1)
    else:
        mes_anterior_inicio = date(hoje.year, hoje.month - 1, 1)

    du_corridos_stmt = select(func.count(DimDiaUtil.id)).where(
        and_(
            DimDiaUtil.tenant_id == tenant_id,
            DimDiaUtil.eh_dia_util.is_(True),
            DimDiaUtil.data >= mes_inicio,
            DimDiaUtil.data <= hoje,
        )
    )
    du_corridos = int((await db.execute(du_corridos_stmt)).scalar_one() or 0)

    du_total_mes_stmt = select(DimDiaUtil.total_dias_uteis_no_mes).where(
        and_(DimDiaUtil.tenant_id == tenant_id, DimDiaUtil.data == mes_inicio)
    )
    du_total_mes = int(
        (await db.execute(du_total_mes_stmt)).scalar_one_or_none() or 0
    )

    if du_corridos == 0 or du_total_mes == 0:
        return None, None

    vop_corrente_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": hoje}
    vop_corrente = await _scalar_sum_volume(
        db, tenant_id, vop_corrente_filters, mes_inicio, hoje
    )

    cutoff_du_stmt = select(DimDiaUtil.data).where(
        and_(
            DimDiaUtil.tenant_id == tenant_id,
            DimDiaUtil.eh_dia_util.is_(True),
            DimDiaUtil.data >= mes_anterior_inicio,
            DimDiaUtil.data < mes_inicio,
            DimDiaUtil.dia_util_index_no_mes == du_corridos,
        )
    )
    cutoff_anterior = (await db.execute(cutoff_du_stmt)).scalar_one_or_none()

    vop_anterior_mesmo_du = 0.0
    if cutoff_anterior:
        vop_anterior_filters = {
            **filters,
            "periodo_inicio": mes_anterior_inicio,
            "periodo_fim": cutoff_anterior,
        }
        vop_anterior_mesmo_du = await _scalar_sum_volume(
            db,
            tenant_id,
            vop_anterior_filters,
            mes_anterior_inicio,
            cutoff_anterior,
        )

    acumulado = await _acumulado_dia_a_dia(
        db, tenant_id, filters, mes_inicio, hoje, mes_anterior_inicio, du_corridos
    )

    projecao = (vop_corrente / du_corridos) * du_total_mes if du_corridos > 0 else 0.0

    delta_pct = (
        _safe_pct_change(vop_corrente, vop_anterior_mesmo_du)
        if vop_anterior_mesmo_du > 0
        else None
    )

    ritmo = RitmoMesCorrente(
        vop_acumulado=vop_corrente,
        du_corridos=du_corridos,
        du_total_mes=du_total_mes,
        vop_anterior_mesmo_du=vop_anterior_mesmo_du,
        delta_pct=delta_pct,
        projecao_fim_mes=projecao,
        acumulado_dia_a_dia=acumulado,
    )

    if mes_anterior_inicio.month == 12:
        mes_anterior_fim = date(mes_anterior_inicio.year + 1, 1, 1) - timedelta(days=1)
    else:
        mes_anterior_fim = date(
            mes_anterior_inicio.year, mes_anterior_inicio.month + 1, 1
        ) - timedelta(days=1)
    vop_anterior_total_filters = {
        **filters,
        "periodo_inicio": mes_anterior_inicio,
        "periodo_fim": mes_anterior_fim,
    }
    vop_anterior_total = await _scalar_sum_volume(
        db, tenant_id, vop_anterior_total_filters, mes_anterior_inicio, mes_anterior_fim
    )
    du_total_anterior_stmt = select(DimDiaUtil.total_dias_uteis_no_mes).where(
        and_(DimDiaUtil.tenant_id == tenant_id, DimDiaUtil.data == mes_anterior_inicio)
    )
    du_total_anterior = int(
        (await db.execute(du_total_anterior_stmt)).scalar_one_or_none() or 0
    )
    vop_du_corrente = vop_corrente / du_corridos
    vop_du_anterior = (
        vop_anterior_total / du_total_anterior if du_total_anterior > 0 else 0.0
    )
    pace = PaceDiario(
        vop_du_corrente=vop_du_corrente,
        vop_du_anterior=vop_du_anterior,
        delta_pct=_safe_pct_change(vop_du_corrente, vop_du_anterior)
        if vop_du_anterior > 0
        else None,
    )
    return ritmo, pace


async def _acumulado_dia_a_dia(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    mes_inicio: date,
    hoje: date,
    mes_anterior_inicio: date,
    du_corridos: int,
) -> list[AcumuladoDiarioPonto]:
    """Serie acumulada dia-a-dia para mini chart corrente vs anterior."""
    if du_corridos == 0:
        return []

    op_data = cast(Operacao.data_de_efetivacao, Date)

    corr_stmt = (
        select(
            DimDiaUtil.dia_util_index_no_mes.label("du_idx"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
        )
        .join(
            DimDiaUtil,
            and_(
                DimDiaUtil.tenant_id == Operacao.tenant_id,
                DimDiaUtil.data == op_data,
            ),
        )
        .where(
            and_(
                Operacao.tenant_id == tenant_id,
                Operacao.efetivada.is_(True),
                op_data >= mes_inicio,
                op_data <= hoje,
                DimDiaUtil.eh_dia_util.is_(True),
            )
        )
        .group_by(DimDiaUtil.dia_util_index_no_mes)
        .order_by(DimDiaUtil.dia_util_index_no_mes)
    )
    corr_rows = (await db.execute(corr_stmt)).all()
    corr_by_idx = {int(r.du_idx): _as_float(r.vop) for r in corr_rows if r.du_idx}

    prev_stmt = (
        select(
            DimDiaUtil.dia_util_index_no_mes.label("du_idx"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
        )
        .join(
            DimDiaUtil,
            and_(
                DimDiaUtil.tenant_id == Operacao.tenant_id,
                DimDiaUtil.data == op_data,
            ),
        )
        .where(
            and_(
                Operacao.tenant_id == tenant_id,
                Operacao.efetivada.is_(True),
                op_data >= mes_anterior_inicio,
                op_data < mes_inicio,
                DimDiaUtil.eh_dia_util.is_(True),
                DimDiaUtil.dia_util_index_no_mes <= du_corridos,
            )
        )
        .group_by(DimDiaUtil.dia_util_index_no_mes)
        .order_by(DimDiaUtil.dia_util_index_no_mes)
    )
    prev_rows = (await db.execute(prev_stmt)).all()
    prev_by_idx = {int(r.du_idx): _as_float(r.vop) for r in prev_rows if r.du_idx}

    acum_corr = 0.0
    acum_prev = 0.0
    out: list[AcumuladoDiarioPonto] = []
    for i in range(1, du_corridos + 1):
        acum_corr += corr_by_idx.get(i, 0.0)
        acum_prev += prev_by_idx.get(i, 0.0)
        out.append(
            AcumuladoDiarioPonto(du_index=i, corrente=acum_corr, anterior=acum_prev)
        )
    return out
