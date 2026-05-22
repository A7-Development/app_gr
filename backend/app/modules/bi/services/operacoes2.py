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

from calendar import monthrange
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Date,
    and_,
    case,
    cast,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bi.schemas.common import Point, Provenance
from app.modules.bi.schemas.operacoes2 import (
    AbaMesCorrenteData,
    AbaMesCorrenteV3Data,
    AbaProdutosPricingData,
    AbaVolumeRitmoData,
    AcumuladoDiarioPonto,
    CedenteMtdItem,
    CedentesMtdData,
    ConcentracaoDeltaData,
    ConcentracaoMovement,
    DriverContribution,
    DumbbellPoint,
    DumbbellSeriesData,
    EvolucaoMensalPonto,
    EvolucaoPorUaPonto,
    HistogramaPrazosResumo,
    HistogramaProdutoBucket,
    HistogramaTaxasResumo,
    KpiCellNumeric,
    KpiCellProduto,
    KpiSecundario,
    KpisSecundariosVolume,
    MesCorrenteKpiCell,
    MesCorrentePotencialCell,
    MesCorrenteTermometro,
    MesDestaque,
    MixTemporalProdutoPonto,
    OperacaoDoDiaItem,
    OperacoesDoDiaData,
    OperacoesKpiStripData,
    PaceDiario,
    ProdutoDestaque,
    ProjectionBridgeData,
    PvmBridgeData,
    QuebraDiaPorDimensao,
    QuebraDimensaoLinha,
    RankingProdutoLinha,
    RitmoMesCorrente,
    RitmoUaItem,
    ScatterProdutoPonto,
    VarianceBridgeData,
    VopDiarioPonto,
    VopDiarioPorUaPonto,
    VopMtdPorUa,
    VopPotencialData,
    VopPotencialPorUa,
)
from app.modules.bi.services.operacoes import (
    _MES_PT,
    _apply_filters,
    _as_float,
    _build_provenance,
    _fmt_comparacao_label_pt,
    _fmt_moeda_compacta_pt,
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
from app.warehouse.caixa_snapshot import CaixaSnapshot
from app.warehouse.dim import DimUnidadeAdministrativa
from app.warehouse.dim_dia_util import DimDiaUtil
from app.warehouse.operacao import Operacao
from app.warehouse.titulo import Titulo

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


def _mes_anterior_window(periodo_fim: date | None) -> tuple[date, date]:
    """Janela MTD do mes anterior — same-period MTD (Month-to-Date).

    Retorna `(1o dia mes-1, dia N do mes-1)` onde N = dia atual do mes
    corrente. Garante comparacao "apples-to-apples" com a janela do mes
    corrente (que tambem vai do dia 1 ao `periodo_fim`).

    Ex.: periodo_fim = 5 mai → retorna (1 abr, 5 abr).
    Edge case: quando o dia atual nao existe no mes anterior (ex.: hoje
    31 mar, mes-1 = fev tem 28/29 dias), clampa para o ultimo dia do
    mes anterior.
    """
    end = periodo_fim or date.today()
    mes_corrente_inicio = end.replace(day=1)
    mes_anterior_ultimo_dia = mes_corrente_inicio - timedelta(days=1)
    mes_anterior_inicio = mes_anterior_ultimo_dia.replace(day=1)
    # Clampa o dia para nao ultrapassar o ultimo dia do mes anterior.
    target_day = min(end.day, mes_anterior_ultimo_dia.day)
    mes_anterior_fim = mes_anterior_inicio.replace(day=target_day)
    return mes_anterior_inicio, mes_anterior_fim


def _sparkline_12m_window(periodo_fim: date | None) -> tuple[date, date]:
    """Calcula a janela 12M (1o dia do mes 11 meses atras → mes corrente).

    Inclui o mes corrente — o ultimo bucket pode ser parcial (MTD) quando
    rodado dentro do mes. Usar `_sparkline_12m_closed_window` quando isso
    distorcer a leitura (ex.: tabela trend de quebra dimensao).
    """
    end = periodo_fim or date.today()
    end_first = end.replace(day=1)
    y, m = end_first.year, end_first.month - 11
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1), end


def _sparkline_12m_closed_window(
    periodo_fim: date | None,
) -> tuple[date, date]:
    """Janela de 12 meses FECHADOS terminando no mes anterior ao periodo_fim.

    Retorna `(1o dia do mes M-12, ultimo dia do mes M-1)` — exatamente 12
    meses cheios, exclui o mes corrente.

    Uso: sparklines de tendencia historica que nao podem incluir o mes
    corrente parcial (MTD) — caso contrario o ultimo bucket sempre apareceria
    como queda brusca quando a pagina e rodada nos primeiros dias do mes,
    distorcendo a leitura de slope. O valor do mes corrente continua exposto
    fora do sparkline (ex.: coluna numerica `pct_mes_corrente` / `vop_mes_corrente`).

    Ex.: periodo_fim = 6 mai 2026 → retorna (1 mai 2025, 30 abr 2026).
    """
    end = periodo_fim or date.today()
    # Ultimo dia do mes anterior ao mes corrente.
    closed_end = end.replace(day=1) - timedelta(days=1)
    # Primeiro dia do M-12 (12 meses antes do mes M-1, inclusivo).
    start_first = closed_end.replace(day=1)
    y, m = start_first.year, start_first.month - 11
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1), closed_end


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

    # ── Agregados MTD same-period do mes anterior (para delta MTD do mes
    #    corrente: maio 1-N vs abril 1-N, com clamp de fim-de-mes). ────────
    mes_ant_inicio, mes_ant_fim = _mes_anterior_window(periodo_fim)
    mes_ant_filters = {
        **filters,
        "periodo_inicio": mes_ant_inicio,
        "periodo_fim": mes_ant_fim,
    }
    agg_mes_anterior = await _agg_kpi(db, tenant_id, mes_ant_filters)

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

    # ── Delta_pp MTD do produto top DO MES (vs share dele no MTD anterior) ─
    produto_top_mes_delta_pp: float | None = None
    if prod_top_mes["sigla"] != "—" and agg_mes_anterior["vop"] > 0:
        mes_ant_p_stmt = _apply_filters(
            select(
                _produto_expr().label("sigla"),
                func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
            ).group_by(_produto_expr()),
            tenant_id=tenant_id,
            **mes_ant_filters,
        )
        mes_ant_p = {
            str(r.sigla or ""): _as_float(r.valor)
            for r in (await db.execute(mes_ant_p_stmt)).all()
        }
        mes_ant_total = sum(mes_ant_p.values())
        if mes_ant_total > 0 and prod_top_mes["sigla"] in mes_ant_p:
            mes_ant_share = mes_ant_p[prod_top_mes["sigla"]] / mes_ant_total * 100
            produto_top_mes_delta_pp = prod_top_mes["share_pct"] - mes_ant_share

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
            mes_corrente_delta_pct=_safe_pct_change(
                agg_mes["vop"], agg_mes_anterior["vop"]
            )
            if agg_mes_anterior["vop"] > 0
            else None,
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
            mes_corrente_delta_pct=_safe_pct_change(
                agg_mes["taxa"], agg_mes_anterior["taxa"]
            )
            if agg_mes_anterior["taxa"] > 0
            else None,
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
            mes_corrente_delta_pct=_safe_pct_change(
                agg_mes["prazo"], agg_mes_anterior["prazo"]
            )
            if agg_mes_anterior["prazo"] > 0
            else None,
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
            mes_corrente_delta_share_pp=produto_top_mes_delta_pp,
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
            mes_corrente_delta_pct=_safe_pct_change(
                agg_mes["receita"], agg_mes_anterior["receita"]
            )
            if agg_mes_anterior["receita"] > 0
            else None,
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

    # Mini-stats: melhor / pior mes
    melhor_mes: MesDestaque | None = None
    pior_mes: MesDestaque | None = None
    if evolucao_12m:
        sorted_by_vop = sorted(evolucao_12m, key=lambda p: p.vop)
        pior_mes = MesDestaque(periodo=sorted_by_vop[0].periodo, vop=sorted_by_vop[0].vop)
        melhor_mes = MesDestaque(periodo=sorted_by_vop[-1].periodo, vop=sorted_by_vop[-1].vop)

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

    kpi_sparks = await _kpi_secundario_sparklines_12m(
        db, tenant_id, filters, periodo_fim, has_du
    )

    vop_du_medio_kpi: KpiSecundario | None = None
    if has_du and ritmo is not None and pace is not None:
        vop_du_medio_kpi = KpiSecundario(
            valor=pace.vop_du_corrente,
            delta_pct=pace.delta_pct,
            sparkline_12m=kpi_sparks["vop_du_medio"],
        )

    kpis_secundarios = KpisSecundariosVolume(
        n_operacoes=KpiSecundario(
            valor=float(n_ops_atual),
            delta_pct=_safe_pct_change(float(n_ops_atual), float(n_ops_prev))
            if n_ops_prev > 0
            else None,
            sparkline_12m=kpi_sparks["n_operacoes"],
        ),
        ticket_op=KpiSecundario(
            valor=ticket_op_atual,
            delta_pct=_safe_pct_change(ticket_op_atual, ticket_op_prev)
            if ticket_op_prev is not None
            else None,
            sparkline_12m=kpi_sparks["ticket_op"],
        ),
        ticket_titulo=KpiSecundario(
            valor=ticket_titulo_atual,
            delta_pct=_safe_pct_change(ticket_titulo_atual, ticket_titulo_prev)
            if ticket_titulo_prev is not None
            else None,
            sparkline_12m=kpi_sparks["ticket_titulo"],
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

    data = AbaVolumeRitmoData(
        evolucao_12m=evolucao_12m,
        evolucao_12m_por_ua=evolucao_12m_por_ua,
        melhor_mes=melhor_mes,
        pior_mes=pior_mes,
        ritmo=ritmo,
        pace_diario=pace,
        kpis_secundarios=kpis_secundarios,
        por_ua=por_ua,
        por_produto=por_produto,
    )
    prov = await _build_provenance(db, tenant_id, filters)
    return data, prov


# ═══════════════════════════════════════════════════════════════════════════
# Helpers de quebra / dia da semana / ritmo
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

    # ── Sparkline 12M de share% / VOP por categoria ──────────────────────
    # Janela de 12 meses FECHADOS (M-12 ate M-1) — exclui o mes corrente.
    # Decisao 2026-05-06: o mes corrente parcial (MTD) gerava queda brusca
    # no ultimo ponto do sparkline durante os primeiros dias do mes,
    # distorcendo a leitura de tendencia. O valor MTD continua exposto via
    # `pct_mes_corrente` / `vop_mes_corrente` (coluna numerica do card),
    # separado do sparkline de tendencia.
    #
    # Diferente das demais agregacoes desta funcao, NAO segue periodo_inicio/
    # periodo_fim do filtro — a leitura aqui e "tendencia historica de 12
    # meses fechados", independente do recorte que o usuario escolheu pro
    # KPI/quebra principal.
    spark_start, spark_end = _sparkline_12m_closed_window(periodo_fim)
    spark_filters = {**filters, "periodo_inicio": spark_start, "periodo_fim": spark_end}
    bucket = func.date_trunc("month", Operacao.data_de_efetivacao)
    spark_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            cat_expr.label("categoria_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
        )
        .group_by(bucket, cat_expr)
        .order_by(bucket),
        tenant_id=tenant_id,
        **spark_filters,
    )
    spark_rows = (await db.execute(spark_stmt)).all()
    monthly_totals: dict[date, float] = {}
    by_cat: dict[str, dict[date, float]] = {}
    for r in spark_rows:
        v = _as_float(r.valor)
        cid_str = cat_to_id_str(r.categoria_id)
        monthly_totals[r.periodo] = monthly_totals.get(r.periodo, 0.0) + v
        by_cat.setdefault(cid_str, {})[r.periodo] = v
    sorted_periods = sorted(monthly_totals.keys())
    spark_share_by_cat: dict[str, list[Point]] = {}
    spark_vop_by_cat: dict[str, list[Point]] = {}
    for cid_str, month_map in by_cat.items():
        spark_share_by_cat[cid_str] = [
            Point(
                periodo=p,
                valor=(month_map.get(p, 0.0) / monthly_totals[p] * 100)
                if monthly_totals.get(p, 0.0) > 0
                else 0.0,
            )
            for p in sorted_periods
        ]
        spark_vop_by_cat[cid_str] = [
            Point(periodo=p, valor=month_map.get(p, 0.0))
            for p in sorted_periods
        ]

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
                sparkline_share_12m=spark_share_by_cat.get(cid_str, []),
                sparkline_vop_12m=spark_vop_by_cat.get(cid_str, []),
            )
        )
    return out


async def _kpi_secundario_sparklines_12m(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    periodo_fim: date | None,
    has_du: bool,
) -> dict[str, list[Point]]:
    """Sparklines 12M fechados para os 4 KPIs secundarios.

    Retorna dict com chaves 'n_operacoes', 'ticket_op', 'ticket_titulo',
    'vop_du_medio'. `vop_du_medio` retorna lista vazia quando
    `wh_dim_dia_util` esta vazia (degraded mode).

    Janela: 12M fechados (M-12 a M-1) — coerente com sparklines da tabela
    trend de quebras, evita o ponto final distorcido pelo MTD parcial.

    Como cada KPI tem unidade/escala diferente (count, BRL, BRL/titulo,
    BRL/DU), o slope deve ser interpretado em modo relativo (% sobre a
    media da serie) — analogo ao card "VOP por UA" mode="absolute".
    """
    spark_start, spark_end = _sparkline_12m_closed_window(periodo_fim)
    spark_filters = {
        **filters,
        "periodo_inicio": spark_start,
        "periodo_fim": spark_end,
    }
    bucket = func.date_trunc("month", Operacao.data_de_efetivacao)

    stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
            func.count(Operacao.id).label("n_ops"),
            func.coalesce(func.sum(Operacao.quantidade_de_titulos), 0).label(
                "n_tits"
            ),
        )
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **spark_filters,
    )
    rows = (await db.execute(stmt)).all()

    spark_n_ops: list[Point] = []
    spark_ticket_op: list[Point] = []
    spark_ticket_tit: list[Point] = []
    vop_by_month: dict[date, float] = {}
    for r in rows:
        v = _as_float(r.vop)
        n = int(r.n_ops or 0)
        t = int(r.n_tits or 0)
        spark_n_ops.append(Point(periodo=r.periodo, valor=float(n)))
        spark_ticket_op.append(
            Point(periodo=r.periodo, valor=(v / n) if n > 0 else 0.0)
        )
        spark_ticket_tit.append(
            Point(periodo=r.periodo, valor=(v / t) if t > 0 else 0.0)
        )
        vop_by_month[r.periodo] = v

    spark_vop_du: list[Point] = []
    if has_du and vop_by_month:
        du_bucket = cast(func.date_trunc("month", DimDiaUtil.data), Date)
        du_stmt = (
            select(
                du_bucket.label("periodo"),
                func.count(DimDiaUtil.id).label("du_total"),
            )
            .where(
                and_(
                    DimDiaUtil.tenant_id == tenant_id,
                    DimDiaUtil.eh_dia_util.is_(True),
                    DimDiaUtil.data >= spark_start,
                    DimDiaUtil.data <= spark_end,
                )
            )
            .group_by(du_bucket)
        )
        du_rows = (await db.execute(du_stmt)).all()
        du_by_month = {r.periodo: int(r.du_total or 0) for r in du_rows}
        for periodo, vop in sorted(vop_by_month.items()):
            du_total = du_by_month.get(periodo, 0)
            spark_vop_du.append(
                Point(
                    periodo=periodo,
                    valor=(vop / du_total) if du_total > 0 else 0.0,
                )
            )

    return {
        "n_operacoes": spark_n_ops,
        "ticket_op": spark_ticket_op,
        "ticket_titulo": spark_ticket_tit,
        "vop_du_medio": spark_vop_du,
    }


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

    ritmo_por_ua = await _calc_ritmo_por_ua(
        db,
        tenant_id,
        filters,
        mes_inicio=mes_inicio,
        hoje=hoje,
        mes_anterior_inicio=mes_anterior_inicio,
        cutoff_anterior=cutoff_anterior,
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
        ritmo_por_ua=ritmo_por_ua,
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
    """Serie acumulada dia-a-dia para mini chart corrente vs anterior.

    Aplica os filtros globais da pagina (`produto_sigla`, `ua_id`, ...) via
    `_apply_filters` para que o mini chart bata com `vop_acumulado` (card
    Projecao) e com os KPIs do strip — ver CLAUDE.md secao 7.2 (filtros
    globais aplicados a TODOS os agregados de uma pagina de BI).
    """
    if du_corridos == 0:
        return []

    op_data = cast(Operacao.data_de_efetivacao, Date)
    join_du = (
        DimDiaUtil,
        and_(
            DimDiaUtil.tenant_id == Operacao.tenant_id,
            DimDiaUtil.data == op_data,
        ),
    )

    # Janela do mes corrente — filtros globais aplicados via _apply_filters.
    corr_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": hoje}
    corr_stmt = _apply_filters(
        select(
            DimDiaUtil.dia_util_index_no_mes.label("du_idx"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
        )
        .join(*join_du)
        .where(DimDiaUtil.eh_dia_util.is_(True))
        .group_by(DimDiaUtil.dia_util_index_no_mes)
        .order_by(DimDiaUtil.dia_util_index_no_mes),
        tenant_id=tenant_id,
        **corr_filters,
    )
    corr_rows = (await db.execute(corr_stmt)).all()
    corr_by_idx = {int(r.du_idx): _as_float(r.vop) for r in corr_rows if r.du_idx}

    # Janela MTD do mes anterior — same-period (apenas DUs ate du_corridos)
    # com os mesmos filtros globais. periodo_fim = vespera do mes_inicio
    # (clamp para `_apply_filters` que usa <= em vez de <).
    prev_filters = {
        **filters,
        "periodo_inicio": mes_anterior_inicio,
        "periodo_fim": mes_inicio - timedelta(days=1),
    }
    prev_stmt = _apply_filters(
        select(
            DimDiaUtil.dia_util_index_no_mes.label("du_idx"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
        )
        .join(*join_du)
        .where(
            and_(
                DimDiaUtil.eh_dia_util.is_(True),
                DimDiaUtil.dia_util_index_no_mes <= du_corridos,
            )
        )
        .group_by(DimDiaUtil.dia_util_index_no_mes)
        .order_by(DimDiaUtil.dia_util_index_no_mes),
        tenant_id=tenant_id,
        **prev_filters,
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


async def _vop_diario_mes_corrente(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    mes_inicio: date,
    mes_fim: date,
    hoje: date,
) -> list[VopDiarioPonto]:
    """Serie diaria de VOP do mes corrente — TODOS os dias do calendario.

    Cobre dia 1 ate o ultimo dia do mes, inclusive sabados, domingos e
    feriados. Dias futuros (`d > hoje`) vem com `vop=None` para que o
    frontend renderize o eixo X completo (placeholder de prazo restante)
    sem desenhar barra.

    `eh_dia_util` vem de `wh_dim_dia_util` quando disponivel; fallback para
    "seg-sex" (weekday < 5) em degraded mode (tabela vazia).

    Aplica os filtros globais da pagina via `_apply_filters` (§7.2): a
    janela temporal local sobrescreve `periodo_inicio`/`periodo_fim` dos
    filtros do usuario, mas `produto_sigla`/`ua_id` continuam vigentes.
    """
    op_data = cast(Operacao.data_de_efetivacao, Date)

    # 1) VOP agregado por dia-calendario (so dias com pelo menos 1 op).
    diario_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": mes_fim}
    diario_stmt = _apply_filters(
        select(
            op_data.label("dia"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
        )
        .group_by(op_data)
        .order_by(op_data),
        tenant_id=tenant_id,
        **diario_filters,
    )
    diario_rows = (await db.execute(diario_stmt)).all()
    vop_by_day: dict[date, float] = {r.dia: _as_float(r.vop) for r in diario_rows}

    # 2) eh_dia_util por dia (tenant calendar) — tolerante a tabela vazia.
    du_stmt = select(DimDiaUtil.data, DimDiaUtil.eh_dia_util).where(
        and_(
            DimDiaUtil.tenant_id == tenant_id,
            DimDiaUtil.data >= mes_inicio,
            DimDiaUtil.data <= mes_fim,
        )
    )
    du_rows = (await db.execute(du_stmt)).all()
    dia_util_by_day: dict[date, bool] = {r.data: bool(r.eh_dia_util) for r in du_rows}

    # 3) Materializa serie densa de TODOS os dias do mes.
    out: list[VopDiarioPonto] = []
    d = mes_inicio
    while d <= mes_fim:
        eh_futuro = d > hoje
        vop = None if eh_futuro else vop_by_day.get(d, 0.0)
        eh_util = dia_util_by_day.get(d, d.weekday() < 5)
        out.append(VopDiarioPonto(data=d, vop=vop, eh_dia_util=eh_util, eh_futuro=eh_futuro))
        d += timedelta(days=1)
    return out


async def _vop_diario_por_ua_mes_corrente(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    mes_inicio: date,
    mes_fim: date,
    hoje: date,
) -> list[VopDiarioPorUaPonto]:
    """VOP por (dia, UA) do mes corrente — alimenta modo 'Por UA' do hero.

    Cobre todos os dias do calendario do mes (mesmo regime do
    `_vop_diario_mes_corrente`), porem quebrado por UA. Apenas UAs com
    pelo menos 1 operacao no mes aparecem na serie — UA sem op nao gera
    linhas (frontend nao precisaria empilhar zeros).

    Aplica filtros globais via `_apply_filters` (§7.2). Mesma janela e
    semantica do `_vop_diario_mes_corrente` para futuro/dia_util.
    """
    op_data = cast(Operacao.data_de_efetivacao, Date)

    # 1) VOP agregado por (dia, UA)
    diario_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": mes_fim}
    stmt = _apply_filters(
        select(
            op_data.label("dia"),
            Operacao.unidade_administrativa_id.label("ua_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
        )
        .where(Operacao.unidade_administrativa_id.is_not(None))
        .group_by(op_data, Operacao.unidade_administrativa_id)
        .order_by(op_data),
        tenant_id=tenant_id,
        **diario_filters,
    )
    rows = (await db.execute(stmt)).all()
    # Index: (dia, ua_id) -> vop
    vop_by_day_ua: dict[tuple[date, int], float] = {
        (r.dia, int(r.ua_id)): _as_float(r.vop) for r in rows
    }
    uas_no_mes: set[int] = {int(r.ua_id) for r in rows}

    # 2) Nomes das UAs (lookup tabela DIM)
    ua_nomes = await _ua_id_to_nome_map(db, tenant_id)

    # 3) eh_dia_util por dia
    du_stmt = select(DimDiaUtil.data, DimDiaUtil.eh_dia_util).where(
        and_(
            DimDiaUtil.tenant_id == tenant_id,
            DimDiaUtil.data >= mes_inicio,
            DimDiaUtil.data <= mes_fim,
        )
    )
    du_rows = (await db.execute(du_stmt)).all()
    dia_util_by_day: dict[date, bool] = {r.data: bool(r.eh_dia_util) for r in du_rows}

    # 4) Materializa serie densa: para cada (dia, UA presente no mes), 1 ponto.
    out: list[VopDiarioPorUaPonto] = []
    uas_sorted = sorted(uas_no_mes)
    d = mes_inicio
    while d <= mes_fim:
        eh_futuro = d > hoje
        eh_util = dia_util_by_day.get(d, d.weekday() < 5)
        for ua_id in uas_sorted:
            vop = None if eh_futuro else vop_by_day_ua.get((d, ua_id), 0.0)
            out.append(
                VopDiarioPorUaPonto(
                    data=d,
                    ua_id=ua_id,
                    ua_nome=ua_nomes.get(ua_id, f"UA {ua_id}"),
                    vop=vop,
                    eh_dia_util=eh_util,
                    eh_futuro=eh_futuro,
                )
            )
        d += timedelta(days=1)
    return out


async def _vop_mtd_por_ua(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    mes_inicio: date,
    hoje: date,
    mes_ant_par_inicio: date,
    mes_ant_par_fim: date,
) -> list[VopMtdPorUa]:
    """VOP MTD + Δ VOP-DU por UA — alimenta header KPI quando o usuario
    seleciona uma UA especifica no card VOP Diario.

    Aplica filtros globais (`_apply_filters` §7.2). 2 queries: MTD corrente
    e MTD same-DU mes anterior. So UAs com VOP MTD > 0 no mes corrente
    aparecem (UAs sem op no MTD nao tem header KPI relevante).
    """
    # MTD corrente por UA
    corr_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": hoje}
    corr_stmt = _apply_filters(
        select(
            Operacao.unidade_administrativa_id.label("ua_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
        )
        .where(Operacao.unidade_administrativa_id.is_not(None))
        .group_by(Operacao.unidade_administrativa_id),
        tenant_id=tenant_id,
        **corr_filters,
    )
    corr_rows = (await db.execute(corr_stmt)).all()
    mtd_por_ua: dict[int, float] = {int(r.ua_id): _as_float(r.vop) for r in corr_rows}

    # MTD same-DU mes anterior por UA (apples-to-apples)
    ant_filters = {
        **filters,
        "periodo_inicio": mes_ant_par_inicio,
        "periodo_fim": mes_ant_par_fim,
    }
    ant_stmt = _apply_filters(
        select(
            Operacao.unidade_administrativa_id.label("ua_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
        )
        .where(Operacao.unidade_administrativa_id.is_not(None))
        .group_by(Operacao.unidade_administrativa_id),
        tenant_id=tenant_id,
        **ant_filters,
    )
    ant_rows = (await db.execute(ant_stmt)).all()
    ant_por_ua: dict[int, float] = {int(r.ua_id): _as_float(r.vop) for r in ant_rows}

    # Resolve nomes
    ua_nomes = await _ua_id_to_nome_map(db, tenant_id)

    out: list[VopMtdPorUa] = []
    for ua_id, valor_mtd in mtd_por_ua.items():
        valor_ant = ant_por_ua.get(ua_id, 0.0)
        if valor_ant > 0:
            delta_pct = ((valor_mtd / valor_ant) - 1.0) * 100.0
        else:
            delta_pct = None
        out.append(
            VopMtdPorUa(
                ua_id=ua_id,
                ua_nome=ua_nomes.get(ua_id, f"UA {ua_id}"),
                valor_mtd=valor_mtd,
                delta_vop_du_pct=delta_pct,
            )
        )
    # Ordena por valor MTD desc (maior UA primeiro).
    out.sort(key=lambda u: u.valor_mtd, reverse=True)
    return out


async def _du_total_mes_de(
    db: AsyncSession, tenant_id: UUID, dia_no_mes: date
) -> int:
    """DUs totais do mes ao qual `dia_no_mes` pertence (via dim_dia_util).

    Retorna 0 quando o calendario nao cobre o mes (degraded mode).
    """
    stmt = (
        select(DimDiaUtil.total_dias_uteis_no_mes)
        .where(
            and_(
                DimDiaUtil.tenant_id == tenant_id,
                DimDiaUtil.data == dia_no_mes,
            )
        )
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    return int(row) if row is not None else 0


async def _calcular_termometro_cells(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    today: date,
    du_decorridos: int,
    du_disponivel: bool,
) -> tuple[
    MesCorrenteKpiCell, MesCorrenteKpiCell, MesCorrenteKpiCell, MesCorrenteKpiCell
]:
    """Calcula os 4 cells absolutos/medios do termometro (VOP, Receita, Taxa, Prazo).

    Cada cell carrega:
      - valor: agregado MTD do mes corrente
      - delta_vop_du_pct: MTD corrente vs MTD mes anterior nos mesmos N DUs
      - delta_mom_pct: ritmo (pace/DU) corrente vs ritmo mes anterior fechado
                      (somente VOP/Receita; Taxa/Prazo comparam medias diretas)

    Aplica filtros globais via `_apply_filters` em todas as queries (§7.2).
    Potencial e calculado separadamente reusando `_calc_vop_potencial`.
    """
    mes_inicio = today.replace(day=1)
    mes_label = f"{_MES_PT[today.month - 1]}/{today.year % 100:02d}"

    # 1. MTD do mes corrente
    mtd_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": today}
    agg_mtd = await _agg_kpi(db, tenant_id, mtd_filters)

    # 2. Mes anterior — paridade DU (apples-to-apples). Degraded => MTD same-day.
    if du_disponivel and du_decorridos > 0:
        mes_ant_par_inicio, mes_ant_par_fim = await _mes_anterior_paridade_du(
            db, tenant_id, today, du_decorridos
        )
    else:
        mes_ant_par_inicio, mes_ant_par_fim = _mes_anterior_window(today)
    ant_par_filters = {
        **filters,
        "periodo_inicio": mes_ant_par_inicio,
        "periodo_fim": mes_ant_par_fim,
    }
    agg_ant_par = await _agg_kpi(db, tenant_id, ant_par_filters)

    # 3. Mes anterior fechado (completo)
    last_day_prev = mes_inicio - timedelta(days=1)
    mes_ant_fechado_inicio = last_day_prev.replace(day=1)
    ant_fech_filters = {
        **filters,
        "periodo_inicio": mes_ant_fechado_inicio,
        "periodo_fim": last_day_prev,
    }
    agg_ant_fech = await _agg_kpi(db, tenant_id, ant_fech_filters)

    # 4. DUs totais do mes anterior fechado (pra pace MoM)
    du_total_ant = (
        await _du_total_mes_de(db, tenant_id, last_day_prev) if du_disponivel else 0
    )

    def _delta_pct(curr: float, base: float) -> float | None:
        if not base:
            return None
        return ((curr / base) - 1.0) * 100.0

    def _build_abs(
        mtd_val: float, ant_par: float, ant_fech: float, unidade: str
    ) -> MesCorrenteKpiCell:
        delta_vop_du = _delta_pct(mtd_val, ant_par) if du_decorridos > 0 else None
        if du_decorridos > 0 and du_total_ant > 0 and ant_fech > 0:
            pace_mtd = mtd_val / du_decorridos
            pace_ant = ant_fech / du_total_ant
            delta_mom = _delta_pct(pace_mtd, pace_ant)
        else:
            delta_mom = None
        return MesCorrenteKpiCell(
            valor=mtd_val,
            delta_vop_du_pct=delta_vop_du,
            delta_mom_pct=delta_mom,
            unidade=unidade,
            mes_label=mes_label,
        )

    def _build_media(
        mtd_val: float, ant_par: float, ant_fech: float, unidade: str
    ) -> MesCorrenteKpiCell:
        # Para medias ponderadas (Taxa, Prazo): comparacao direta media-vs-media
        # em ambos os deltas. Sem normalizacao por DU.
        return MesCorrenteKpiCell(
            valor=mtd_val,
            delta_vop_du_pct=_delta_pct(mtd_val, ant_par),
            delta_mom_pct=_delta_pct(mtd_val, ant_fech),
            unidade=unidade,
            mes_label=mes_label,
        )

    vop_cell = _build_abs(agg_mtd["vop"], agg_ant_par["vop"], agg_ant_fech["vop"], "BRL")
    receita_cell = _build_abs(
        agg_mtd["receita"], agg_ant_par["receita"], agg_ant_fech["receita"], "BRL"
    )
    taxa_cell = _build_media(
        agg_mtd["taxa"], agg_ant_par["taxa"], agg_ant_fech["taxa"], "%"
    )
    prazo_cell = _build_media(
        agg_mtd["prazo"], agg_ant_par["prazo"], agg_ant_fech["prazo"], "dias"
    )
    return vop_cell, receita_cell, taxa_cell, prazo_cell


async def _calc_ritmo_por_ua(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    *,
    mes_inicio: date,
    hoje: date,
    mes_anterior_inicio: date,
    cutoff_anterior: date | None,
) -> list[RitmoUaItem]:
    """Quebra do ritmo do mes corrente por UA.

    Para cada UA presente no resultado filtrado, calcula:
      - vop_corrente: VOP MTD da UA (mes corrente, dia 1 a `hoje`)
      - vop_anterior_mesmo_du: VOP MTD do mes anterior ate `cutoff_anterior`
        (mesmo numero de DUs corridos)
      - delta_pct: variacao apples-to-apples
    Ordenado por vop_corrente DESC. Retorna vazio quando nao ha UA nos
    filtros ou quando a query nao volta linhas.
    """
    # MTD corrente por UA
    corr_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": hoje}
    corr_stmt = _apply_filters(
        select(
            Operacao.unidade_administrativa_id.label("ua_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
        ).group_by(Operacao.unidade_administrativa_id),
        tenant_id=tenant_id,
        **corr_filters,
    )
    corr_rows = (await db.execute(corr_stmt)).all()
    corr_by_ua = {
        int(r.ua_id): _as_float(r.vop) for r in corr_rows if r.ua_id is not None
    }

    if not corr_by_ua:
        return []

    # MTD anterior (apples-to-apples ate o N-esimo DU) por UA
    prev_by_ua: dict[int, float] = {}
    if cutoff_anterior is not None:
        prev_filters = {
            **filters,
            "periodo_inicio": mes_anterior_inicio,
            "periodo_fim": cutoff_anterior,
        }
        prev_stmt = _apply_filters(
            select(
                Operacao.unidade_administrativa_id.label("ua_id"),
                func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
            ).group_by(Operacao.unidade_administrativa_id),
            tenant_id=tenant_id,
            **prev_filters,
        )
        prev_rows = (await db.execute(prev_stmt)).all()
        prev_by_ua = {
            int(r.ua_id): _as_float(r.vop) for r in prev_rows if r.ua_id is not None
        }

    ua_nomes = await _ua_id_to_nome_map(db, tenant_id)

    items: list[RitmoUaItem] = []
    for ua_id, vop in sorted(corr_by_ua.items(), key=lambda kv: kv[1], reverse=True):
        prev = prev_by_ua.get(ua_id, 0.0)
        items.append(
            RitmoUaItem(
                ua_id=ua_id,
                ua_nome=ua_nomes.get(ua_id, f"UA {ua_id}"),
                vop_corrente=vop,
                delta_pct=_safe_pct_change(vop, prev) if prev > 0 else None,
            )
        )
    return items


# ═══════════════════════════════════════════════════════════════════════════
# Endpoint 3 — Aba 2: Produtos & Pricing
# ═══════════════════════════════════════════════════════════════════════════


# Buckets fixos do histograma de prazos (dias).
_PRAZO_BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.0, 30.0, "0-30 d"),
    (30.0, 60.0, "31-60 d"),
    (60.0, 90.0, "61-90 d"),
    (90.0, 180.0, "91-180 d"),
    (180.0, float("inf"), "180+ d"),
)


async def get_aba2_produtos_pricing(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[AbaProdutosPricingData, Provenance]:
    """Bundle completo da Aba 2 — Produtos & Pricing.

    Estrutura paralela a `get_aba1_volume_ritmo`. TODA query passa por
    `_apply_filters` (regra dura §7.2 do CLAUDE.md). Sem excecao.
    """
    periodo_inicio: date | None = filters.get("periodo_inicio")
    periodo_fim: date | None = filters.get("periodo_fim")

    # ── L1: mix temporal — respeita 100% dos filtros globais (§7.2). ───────
    # Hero da aba; bucketizado por mes via date_trunc no proprio query. A
    # janela do usuario (preset/custom) determina quantas barras aparecem.
    mix_temporal_12m = await _mix_temporal_produtos(db, tenant_id, filters)

    # ── L2: ranking (periodo + MTD same-period do mes corrente) ────────────
    mes_inicio, mes_fim, _mes_label = _mes_corrente_window(periodo_fim)
    mes_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": mes_fim}
    ranking = await _ranking_produtos(
        db, tenant_id, filters, mes_filters, periodo_inicio, periodo_fim
    )

    # ── Scatter agregado: subset do ranking (sem nova query) ───────────────
    scatter_produtos = [
        ScatterProdutoPonto(
            sigla=r.sigla,
            nome=r.nome,
            prazo_medio=r.prazo_medio,
            taxa_media=r.taxa_media,
            vop=r.vop,
            prazo_medio_mes_corrente=0.0,  # populado em segundo passe abaixo
            taxa_media_mes_corrente=0.0,
            vop_mes_corrente=r.vop_mes_corrente,
        )
        for r in ranking
    ]
    # Segundo passe: prazo/taxa do mes corrente por produto.
    if ranking:
        prazo_taxa_mes = await _prazo_taxa_mes_por_produto(db, tenant_id, mes_filters)
        for sp in scatter_produtos:
            pt = prazo_taxa_mes.get(sp.sigla)
            if pt:
                sp.prazo_medio_mes_corrente = pt[0]
                sp.taxa_media_mes_corrente = pt[1]

    # ── L3: histogramas ────────────────────────────────────────────────────
    histograma_taxas = await _histograma_taxas(db, tenant_id, filters)
    histograma_prazos = await _histograma_prazos(db, tenant_id, filters)

    # ── Mini-stats (lider, maior alta/queda MoM) — pos-processamento ──────
    lider, alta, queda = _lider_alta_queda(ranking)

    data = AbaProdutosPricingData(
        mix_temporal_12m=mix_temporal_12m,
        lider_periodo=lider,
        maior_alta_mom=alta,
        maior_queda_mom=queda,
        ranking=ranking,
        scatter_produtos=scatter_produtos,
        histograma_taxas=histograma_taxas,
        histograma_prazos=histograma_prazos,
    )
    prov = await _build_provenance(db, tenant_id, filters)
    return data, prov


async def _mix_temporal_produtos(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> list[MixTemporalProdutoPonto]:
    """Serie 12M fechados quebrada por produto (stacked bar do Hero L1)."""
    bucket = func.date_trunc("month", Operacao.data_de_efetivacao)
    stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            _produto_expr().label("sigla"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
            func.coalesce(func.count(Operacao.id), 0).label("n_ops"),
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("taxa"),
            _weighted_avg(Operacao.prazo_medio_real, Operacao.total_bruto).label("prazo"),
        )
        .group_by(bucket, _produto_expr())
        .order_by(bucket, _produto_expr()),
        tenant_id=tenant_id,
        **filters,
    )
    rows = (await db.execute(stmt)).all()
    return [
        MixTemporalProdutoPonto(
            periodo=r.periodo.isoformat(),
            produto_sigla=str(r.sigla or "(n/d)"),
            vop=_as_float(r.vop),
            n_operacoes=int(r.n_ops or 0),
            taxa_media=_as_float(r.taxa) if r.taxa is not None else 0.0,
            prazo_medio=_as_float(r.prazo) if r.prazo is not None else 0.0,
        )
        for r in rows
    ]


async def _ranking_produtos(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    mes_filters: dict[str, Any],
    periodo_inicio: date | None,
    periodo_fim: date | None,
) -> list[RankingProdutoLinha]:
    """Ranking com share, MoM em pp, taxa/prazo/spread ponderados, n_ops + MTD."""
    nomes_map = await _produto_sigla_to_nome_map(db, tenant_id)

    # ── Periodo (filtro) ──────────────────────────────────────────────────
    stmt_periodo = _apply_filters(
        select(
            _produto_expr().label("sigla"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
            func.coalesce(func.count(Operacao.id), 0).label("n_ops"),
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("taxa"),
            _weighted_avg(Operacao.prazo_medio_real, Operacao.total_bruto).label("prazo"),
            _weighted_avg(Operacao.spread, Operacao.total_bruto).label("spread"),
        )
        .group_by(_produto_expr())
        .order_by(func.sum(Operacao.total_bruto).desc()),
        tenant_id=tenant_id,
        **filters,
    )
    periodo_rows = (await db.execute(stmt_periodo)).all()
    vop_total_periodo = sum(_as_float(r.vop) for r in periodo_rows)

    # ── Mes corrente: VOP por produto (apenas snapshot, sem agregar tudo) ─
    stmt_mes = _apply_filters(
        select(
            _produto_expr().label("sigla"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("taxa"),
        ).group_by(_produto_expr()),
        tenant_id=tenant_id,
        **mes_filters,
    )
    mes_map: dict[str, tuple[float, float]] = {
        str(r.sigla or "(n/d)"): (
            _as_float(r.vop),
            _as_float(r.taxa) if r.taxa is not None else 0.0,
        )
        for r in (await db.execute(stmt_mes)).all()
    }

    # ── Periodo anterior (mesmo tamanho) — para delta_mom_pp em share ─────
    prev_inicio, prev_fim = _shift_period_back(periodo_inicio, periodo_fim)
    prev_share_map: dict[str, float] = {}
    if prev_inicio and prev_fim:
        prev_filters = {**filters, "periodo_inicio": prev_inicio, "periodo_fim": prev_fim}
        prev_stmt = _apply_filters(
            select(
                _produto_expr().label("sigla"),
                func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
            ).group_by(_produto_expr()),
            tenant_id=tenant_id,
            **prev_filters,
        )
        prev_rows = (await db.execute(prev_stmt)).all()
        prev_total = sum(_as_float(r.vop) for r in prev_rows)
        if prev_total > 0:
            prev_share_map = {
                str(r.sigla or "(n/d)"): _as_float(r.vop) / prev_total * 100
                for r in prev_rows
            }

    # ── Monta linhas ──────────────────────────────────────────────────────
    out: list[RankingProdutoLinha] = []
    for r in periodo_rows:
        sigla = str(r.sigla or "(n/d)")
        vop = _as_float(r.vop)
        pct = (vop / vop_total_periodo * 100) if vop_total_periodo > 0 else 0.0
        prev_share = prev_share_map.get(sigla)
        delta_mom_pp = pct - prev_share if prev_share is not None else None
        mes_vop, mes_taxa = mes_map.get(sigla, (0.0, 0.0))
        out.append(
            RankingProdutoLinha(
                sigla=sigla,
                nome=nomes_map.get(sigla),
                vop=vop,
                pct=pct,
                delta_mom_pp=delta_mom_pp,
                taxa_media=_as_float(r.taxa) if r.taxa is not None else 0.0,
                prazo_medio=_as_float(r.prazo) if r.prazo is not None else 0.0,
                spread_medio=_as_float(r.spread) if r.spread is not None else 0.0,
                n_operacoes=int(r.n_ops or 0),
                vop_mes_corrente=mes_vop,
                taxa_media_mes_corrente=mes_taxa,
            )
        )
    return out


async def _prazo_taxa_mes_por_produto(
    db: AsyncSession, tenant_id: UUID, mes_filters: dict[str, Any]
) -> dict[str, tuple[float, float]]:
    """Retorna `{sigla: (prazo_medio, taxa_media)}` no MTD do mes corrente."""
    stmt = _apply_filters(
        select(
            _produto_expr().label("sigla"),
            _weighted_avg(Operacao.prazo_medio_real, Operacao.total_bruto).label("prazo"),
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("taxa"),
        ).group_by(_produto_expr()),
        tenant_id=tenant_id,
        **mes_filters,
    )
    return {
        str(r.sigla or "(n/d)"): (
            _as_float(r.prazo) if r.prazo is not None else 0.0,
            _as_float(r.taxa) if r.taxa is not None else 0.0,
        )
        for r in (await db.execute(stmt)).all()
    }


def _bucket_size_taxas(min_taxa: float, max_taxa: float) -> float:
    """Bucket dinamico: 0.25 pp se range <= 5pp, 0.5 pp se > 5pp.

    Clampa em ~30 buckets para evitar histograma serrilhado em ranges enormes.
    """
    rng = max_taxa - min_taxa
    if rng <= 0:
        return 0.25
    size = 0.25 if rng <= 5.0 else 0.5
    # Evita > 30 buckets em ranges atipicos (ex.: outliers em CDC).
    while rng / size > 30 and size < 5.0:
        size *= 2
    return size


async def _histograma_taxas(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> HistogramaTaxasResumo:
    """Histograma de taxas com bucket dinamico, quebrado por produto.

    Mediana e aproximada por bucketing — ponto central do bucket onde o
    cumsum de VOP cruza 50%. Aproximacao adequada para leitura visual;
    issue futura caso precisemos da mediana exata ponderada.
    """
    # Min/max para dimensionar bucket dinamico.
    range_stmt = _apply_filters(
        select(
            func.min(Operacao.taxa_de_juros).label("min_t"),
            func.max(Operacao.taxa_de_juros).label("max_t"),
        ),
        tenant_id=tenant_id,
        **filters,
    )
    rng_row = (await db.execute(range_stmt)).one()
    min_t = _as_float(rng_row.min_t) if rng_row.min_t is not None else 0.0
    max_t = _as_float(rng_row.max_t) if rng_row.max_t is not None else 0.0
    bucket_size = _bucket_size_taxas(min_t, max_t)

    # Bucketiza em SQL: floor((taxa - origin) / size) * size + origin como lower.
    origin = float(int(min_t / bucket_size) * bucket_size)
    lower_expr = (
        func.floor((Operacao.taxa_de_juros - origin) / bucket_size) * bucket_size + origin
    )
    stmt = _apply_filters(
        select(
            lower_expr.label("lower"),
            _produto_expr().label("sigla"),
            func.coalesce(func.count(Operacao.id), 0).label("count"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("media_pond"),
        )
        .group_by(lower_expr, _produto_expr())
        .order_by(lower_expr, _produto_expr()),
        tenant_id=tenant_id,
        **filters,
    )
    rows = (await db.execute(stmt)).all()

    buckets: list[HistogramaProdutoBucket] = []
    for r in rows:
        lower = _as_float(r.lower)
        upper = lower + bucket_size
        buckets.append(
            HistogramaProdutoBucket(
                produto_sigla=str(r.sigla or "(n/d)"),
                bucket_label=f"{lower:.2f}-{upper:.2f}%",
                bucket_lower=lower,
                bucket_upper=upper,
                count=int(r.count or 0),
                vop=_as_float(r.vop),
            )
        )

    # Media ponderada global (1 query separada — agrega tudo em 1 row).
    media_stmt = _apply_filters(
        select(
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("media"),
        ),
        tenant_id=tenant_id,
        **filters,
    )
    media_row = (await db.execute(media_stmt)).one()
    media = _as_float(media_row.media) if media_row.media is not None else 0.0

    # Mediana aproximada: bucket onde cumsum de VOP atinge 50% do total.
    by_lower: dict[float, float] = {}
    for b in buckets:
        by_lower[b.bucket_lower] = by_lower.get(b.bucket_lower, 0.0) + b.vop
    total_vop = sum(by_lower.values())
    mediana = 0.0
    if total_vop > 0:
        target = total_vop / 2
        cum = 0.0
        for lower in sorted(by_lower.keys()):
            cum += by_lower[lower]
            if cum >= target:
                mediana = lower + bucket_size / 2
                break

    return HistogramaTaxasResumo(
        buckets=buckets,
        media_ponderada=media,
        mediana=mediana,
        bucket_size_pp=bucket_size,
    )


async def _histograma_prazos(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> HistogramaPrazosResumo:
    """Histograma de prazos com buckets fixos (0-30, 31-60, 61-90, 91-180, 180+)."""
    # Cria CASE WHEN para bucketizacao em SQL — uma row por (bucket, produto).
    # Buckets sao expostos como pares (lower, upper, label).
    stmt = _apply_filters(
        select(
            Operacao.prazo_medio_real.label("prazo"),
            _produto_expr().label("sigla"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
            func.coalesce(func.count(Operacao.id), 0).label("count"),
        ).group_by(Operacao.prazo_medio_real, _produto_expr()),
        tenant_id=tenant_id,
        **filters,
    )
    rows = (await db.execute(stmt)).all()

    # Agrega em Python usando os buckets fixos definidos em _PRAZO_BUCKETS.
    # Mais simples e nao requer CASE WHEN gigante em SQL — volume ja e
    # menor (1 row por valor distinto de prazo, nao por operacao).
    accum: dict[tuple[str, int], dict[str, float | int]] = {}
    for r in rows:
        prazo = _as_float(r.prazo) if r.prazo is not None else 0.0
        sigla = str(r.sigla or "(n/d)")
        bucket_idx = next(
            (i for i, (lo, hi, _) in enumerate(_PRAZO_BUCKETS) if lo <= prazo < hi),
            len(_PRAZO_BUCKETS) - 1,  # cai no "180+"
        )
        key = (sigla, bucket_idx)
        if key not in accum:
            accum[key] = {"count": 0, "vop": 0.0}
        accum[key]["count"] = int(accum[key]["count"]) + int(r.count or 0)
        accum[key]["vop"] = float(accum[key]["vop"]) + _as_float(r.vop)

    buckets: list[HistogramaProdutoBucket] = []
    for (sigla, bucket_idx), agg in sorted(accum.items()):
        lo, hi, label = _PRAZO_BUCKETS[bucket_idx]
        buckets.append(
            HistogramaProdutoBucket(
                produto_sigla=sigla,
                bucket_label=label,
                bucket_lower=lo,
                bucket_upper=hi if hi != float("inf") else 9999.0,
                count=int(agg["count"]),
                vop=float(agg["vop"]),
            )
        )
    return HistogramaPrazosResumo(buckets=buckets)


def _lider_alta_queda(
    ranking: list[RankingProdutoLinha],
) -> tuple[ProdutoDestaque | None, ProdutoDestaque | None, ProdutoDestaque | None]:
    """Mini-stats do rodape do Hero: lider de share, maior alta MoM, maior queda MoM."""
    if not ranking:
        return None, None, None

    lider_row = max(ranking, key=lambda r: r.pct)
    lider = ProdutoDestaque(
        sigla=lider_row.sigla, nome=lider_row.nome, valor=lider_row.pct
    )

    com_delta = [r for r in ranking if r.delta_mom_pp is not None]
    alta: ProdutoDestaque | None = None
    queda: ProdutoDestaque | None = None
    if com_delta:
        alta_row = max(com_delta, key=lambda r: r.delta_mom_pp or 0.0)
        if (alta_row.delta_mom_pp or 0.0) > 0:
            alta = ProdutoDestaque(
                sigla=alta_row.sigla,
                nome=alta_row.nome,
                valor=alta_row.delta_mom_pp or 0.0,
            )
        queda_row = min(com_delta, key=lambda r: r.delta_mom_pp or 0.0)
        if (queda_row.delta_mom_pp or 0.0) < 0:
            queda = ProdutoDestaque(
                sigla=queda_row.sigla,
                nome=queda_row.nome,
                valor=queda_row.delta_mom_pp or 0.0,
            )
    return lider, alta, queda


# ═══════════════════════════════════════════════════════════════════════════
# Aba 0 — Mes Corrente (variance decomposition)
# ═══════════════════════════════════════════════════════════════════════════
#
# Decompoe o delta MTD (mes corrente ate periodo_fim) vs DU equivalente do
# mes anterior em 6 KPIs com tecnicas adequadas:
#   - VOP / Receita     -> Variance bridge aditiva + projecao linear
#   - Taxa / Prazo      -> PVM bridge (mix effect + intra effect, Marshall-
#                          Edgeworth)
#   - Mix produtos      -> Dumbbell prior_share vs current_share
#   - Concentracao      -> HHI delta + top movements de share
#
# Threshold de surfacing: max(R$500k absoluto, 5%% do |delta_total|).
# Drivers abaixo rolam em "Outros".

# Threshold para drivers (CLAUDE.md decisao 2026-05-08).
_DRIVER_THRESHOLD_PCT = 0.05
_DRIVER_THRESHOLD_BRL = 500_000.0

# Threshold para PVM (em unidade do KPI) — calibrado pro contexto FIDC.
_PVM_THRESHOLD_TAXA_PP = 0.05  # 0.05 pp
_PVM_THRESHOLD_PRAZO_DIAS = 0.5  # meio dia


def _faixa_ticket_expr() -> ColumnElement[str]:
    """CASE WHEN classificando operacao em faixa de ticket por total_bruto."""
    return case(
        (Operacao.total_bruto < 50_000, "≤ R$ 50k"),
        (Operacao.total_bruto < 250_000, "R$ 50k-250k"),
        (Operacao.total_bruto < 1_000_000, "R$ 250k-1M"),
        (Operacao.total_bruto < 5_000_000, "R$ 1M-5M"),
        else_="> R$ 5M",
    )


async def _du_position(
    db: AsyncSession, tenant_id: UUID, today: date
) -> tuple[bool, int, int]:
    """Retorna (du_disponivel, du_decorridos, du_totais_mes).

    Quando wh_dim_dia_util esta vazia ou nao cobre o mes corrente, retorna
    (False, 0, 0) — pagina degrada para paridade de dia corrido.
    """
    has_du = await _has_dim_dia_util(db, tenant_id)
    if not has_du:
        return False, 0, 0

    mes_inicio = today.replace(day=1)

    decorridos_stmt = select(func.count(DimDiaUtil.id)).where(
        and_(
            DimDiaUtil.tenant_id == tenant_id,
            DimDiaUtil.eh_dia_util.is_(True),
            DimDiaUtil.data >= mes_inicio,
            DimDiaUtil.data <= today,
        )
    )
    du_decorridos = int((await db.execute(decorridos_stmt)).scalar_one() or 0)

    total_stmt = (
        select(DimDiaUtil.total_dias_uteis_no_mes)
        .where(
            and_(
                DimDiaUtil.tenant_id == tenant_id,
                DimDiaUtil.data == today,
            )
        )
        .limit(1)
    )
    total_row = (await db.execute(total_stmt)).scalar_one_or_none()
    if total_row is None:
        # `today` fora do calendario carregado — degraded
        return False, du_decorridos, 0
    return True, du_decorridos, int(total_row)


async def _mes_anterior_paridade_du(
    db: AsyncSession,
    tenant_id: UUID,
    today: date,
    du_decorridos: int,
) -> tuple[date, date]:
    """Janela do mes anterior com mesmo numero de DUs decorridos.

    Ex.: hoje=8 mai, du_decorridos=6 -> retorna (1 abr, data do 6o DU de abr).

    Edge: mes anterior com menos DUs que `du_decorridos` (raro, feriados
    concentrados) -> clampa para o ultimo DU do mes anterior.
    """
    mes_inicio = today.replace(day=1)
    mes_anterior_ultimo_dia = mes_inicio - timedelta(days=1)
    mes_anterior_inicio = mes_anterior_ultimo_dia.replace(day=1)

    target_stmt = select(DimDiaUtil.data).where(
        and_(
            DimDiaUtil.tenant_id == tenant_id,
            DimDiaUtil.data >= mes_anterior_inicio,
            DimDiaUtil.data <= mes_anterior_ultimo_dia,
            DimDiaUtil.eh_dia_util.is_(True),
            DimDiaUtil.dia_util_index_no_mes == du_decorridos,
        )
    )
    target = (await db.execute(target_stmt)).scalar_one_or_none()
    if target is None:
        # Fallback: ultimo DU do mes anterior
        last_stmt = (
            select(DimDiaUtil.data)
            .where(
                and_(
                    DimDiaUtil.tenant_id == tenant_id,
                    DimDiaUtil.data >= mes_anterior_inicio,
                    DimDiaUtil.data <= mes_anterior_ultimo_dia,
                    DimDiaUtil.eh_dia_util.is_(True),
                )
            )
            .order_by(DimDiaUtil.data.desc())
            .limit(1)
        )
        target = (await db.execute(last_stmt)).scalar_one_or_none()
        if target is None:
            return mes_anterior_inicio, mes_anterior_ultimo_dia
    return mes_anterior_inicio, target


async def _agg_by_dimension(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    dimension: str,
) -> dict[str, dict[str, float]]:
    """Agrega VOP/Receita/Taxa/Prazo por membro da dimensao.

    Retorna {member_id_str: {vop, receita, taxa, prazo}}. Membros sem
    volume sao excluidos. Aplica `_apply_filters` (CLAUDE.md §7.2).

    `dimension` aceita "produto" | "ua" | "faixa_ticket".
    """
    if dimension == "produto":
        cat_expr: ColumnElement[Any] = _produto_expr()
    elif dimension == "ua":
        cat_expr = Operacao.unidade_administrativa_id
    elif dimension == "faixa_ticket":
        cat_expr = _faixa_ticket_expr()
    else:
        raise ValueError(f"Dimensao desconhecida: {dimension}")

    stmt = _apply_filters(
        select(
            cat_expr.label("member_id"),
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
        ).group_by(cat_expr),
        tenant_id=tenant_id,
        **filters,
    )
    rows = (await db.execute(stmt)).all()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        member_id = str(r.member_id) if r.member_id is not None else "(n/d)"
        vop = _as_float(r.vop)
        if vop <= 0:
            continue
        out[member_id] = {
            "vop": vop,
            "receita": _as_float(r.receita),
            "taxa": _as_float(r.taxa) if r.taxa is not None else 0.0,
            "prazo": _as_float(r.prazo) if r.prazo is not None else 0.0,
        }
    return out


def _decompose_variance_aditiva(
    prior_by_member: dict[str, float],
    current_by_member: dict[str, float],
    label_resolver: Callable[[str], str],
    threshold_pct: float = _DRIVER_THRESHOLD_PCT,
    threshold_brl: float = _DRIVER_THRESHOLD_BRL,
) -> tuple[list[DriverContribution], DriverContribution | None, float]:
    """Decompoe delta de metrica aditiva (VOP, Receita) em drivers + outros.

    Retorna (drivers, outros_rollup, delta_total).
    Threshold absoluto = max(threshold_brl, threshold_pct * |delta|).
    """
    all_members = set(prior_by_member.keys()) | set(current_by_member.keys())
    delta_total = sum(current_by_member.values()) - sum(prior_by_member.values())
    abs_delta = abs(delta_total)
    threshold_abs = max(threshold_brl, threshold_pct * abs_delta)

    drivers: list[DriverContribution] = []
    outros_prior_sum = 0.0
    outros_current_sum = 0.0

    for member_id in all_members:
        prior = prior_by_member.get(member_id, 0.0)
        current = current_by_member.get(member_id, 0.0)
        contrib = current - prior
        if abs(contrib) < threshold_abs:
            outros_prior_sum += prior
            outros_current_sum += current
            continue
        drivers.append(
            DriverContribution(
                member_id=member_id,
                member_label=label_resolver(member_id),
                contribution_brl=contrib,
                contribution_pct=(contrib / abs_delta * 100) if abs_delta > 0 else None,
                prior_value=prior,
                current_value=current,
            )
        )

    drivers.sort(key=lambda d: abs(d.contribution_brl), reverse=True)
    outros: DriverContribution | None = None
    outros_contrib = outros_current_sum - outros_prior_sum
    if outros_prior_sum > 0 or outros_current_sum > 0:
        outros = DriverContribution(
            member_id="__outros__",
            member_label="Outros",
            contribution_brl=outros_contrib,
            contribution_pct=(outros_contrib / abs_delta * 100) if abs_delta > 0 else None,
            prior_value=outros_prior_sum,
            current_value=outros_current_sum,
        )
    return drivers, outros, delta_total


def _decompose_pvm(
    prior_by_member: dict[str, dict[str, float]],
    current_by_member: dict[str, dict[str, float]],
    value_key: str,
    label_resolver: Callable[[str], str],
    threshold_unit: float,
) -> tuple[
    float,
    float,
    list[DriverContribution],
    list[DriverContribution],
    DriverContribution | None,
    DriverContribution | None,
]:
    """Decompoe delta de media ponderada em mix + intra (Marshall-Edgeworth).

    mix_effect_i   = (current_share_i - prior_share_i) * prior_avg_i
    intra_effect_i = current_share_i * (current_avg_i - prior_avg_i)
    delta_total = sum(mix_effect_i) + sum(intra_effect_i) = current_avg - prior_avg

    Threshold em unidade do KPI (pp pra Taxa, dias pra Prazo).

    Retorna (mix_total, intra_total, top_mix, top_intra, outros_mix, outros_intra).
    """
    prior_total_vop = sum(d["vop"] for d in prior_by_member.values()) or 1e-9
    current_total_vop = sum(d["vop"] for d in current_by_member.values()) or 1e-9
    all_members = set(prior_by_member.keys()) | set(current_by_member.keys())

    mix_contribs: list[tuple[str, float, float, float]] = []
    intra_contribs: list[tuple[str, float, float, float]] = []
    mix_total = 0.0
    intra_total = 0.0

    for member_id in all_members:
        p = prior_by_member.get(member_id, {"vop": 0.0, value_key: 0.0})
        c = current_by_member.get(member_id, {"vop": 0.0, value_key: 0.0})
        prior_share = p["vop"] / prior_total_vop
        current_share = c["vop"] / current_total_vop
        prior_avg = p.get(value_key, 0.0)
        current_avg = c.get(value_key, 0.0)
        mix_e = (current_share - prior_share) * prior_avg
        intra_e = current_share * (current_avg - prior_avg)
        mix_total += mix_e
        intra_total += intra_e
        mix_contribs.append((member_id, mix_e, prior_avg, current_avg))
        intra_contribs.append((member_id, intra_e, prior_avg, current_avg))

    abs_delta_total = abs(mix_total) + abs(intra_total)

    def _filter(
        items: list[tuple[str, float, float, float]],
    ) -> tuple[list[DriverContribution], DriverContribution | None]:
        kept: list[DriverContribution] = []
        outros_n = 0
        outros_prior_sum = 0.0
        outros_curr_sum = 0.0
        outros_contrib_sum = 0.0
        for member_id, contrib, prior_avg, current_avg in items:
            if abs(contrib) < threshold_unit:
                outros_n += 1
                outros_prior_sum += prior_avg
                outros_curr_sum += current_avg
                outros_contrib_sum += contrib
                continue
            kept.append(
                DriverContribution(
                    member_id=member_id,
                    member_label=label_resolver(member_id),
                    contribution_brl=contrib,
                    contribution_pct=(
                        abs(contrib) / abs_delta_total * 100
                    )
                    if abs_delta_total > 0
                    else None,
                    prior_value=prior_avg,
                    current_value=current_avg,
                )
            )
        kept.sort(key=lambda d: abs(d.contribution_brl), reverse=True)
        outros: DriverContribution | None = None
        if outros_n > 0:
            outros = DriverContribution(
                member_id="__outros__",
                member_label="Outros",
                contribution_brl=outros_contrib_sum,
                contribution_pct=None,
                prior_value=outros_prior_sum / outros_n if outros_n > 0 else 0.0,
                current_value=outros_curr_sum / outros_n if outros_n > 0 else 0.0,
            )
        return kept, outros

    mix_drivers, mix_outros = _filter(mix_contribs)
    intra_drivers, intra_outros = _filter(intra_contribs)
    return mix_total, intra_total, mix_drivers, intra_drivers, mix_outros, intra_outros


def _build_dumbbell(
    prior_by_produto: dict[str, dict[str, float]],
    current_by_produto: dict[str, dict[str, float]],
    label_resolver: Callable[[str], str],
    top_n: int = 7,
) -> list[DumbbellPoint]:
    """Pontos de dumbbell: prior_share vs current_share por produto.

    Filtra produtos com share < 1%% em ambos os periodos (ruido).
    Ordena por |delta_share_pp| desc, retorna top N.
    """
    prior_total = sum(d["vop"] for d in prior_by_produto.values()) or 1e-9
    current_total = sum(d["vop"] for d in current_by_produto.values()) or 1e-9
    all_members = set(prior_by_produto.keys()) | set(current_by_produto.keys())

    points: list[DumbbellPoint] = []
    for member_id in all_members:
        p_vop = prior_by_produto.get(member_id, {"vop": 0.0})["vop"]
        c_vop = current_by_produto.get(member_id, {"vop": 0.0})["vop"]
        p_share = p_vop / prior_total * 100
        c_share = c_vop / current_total * 100
        if p_share < 1.0 and c_share < 1.0:
            continue
        points.append(
            DumbbellPoint(
                member_id=member_id,
                member_label=label_resolver(member_id),
                prior_share_pct=p_share,
                current_share_pct=c_share,
                delta_share_pp=c_share - p_share,
                prior_value=p_vop,
                current_value=c_vop,
            )
        )
    points.sort(key=lambda p: abs(p.delta_share_pp), reverse=True)
    return points[:top_n]


def _calcular_hhi_e_movements(
    prior_by_produto: dict[str, dict[str, float]],
    current_by_produto: dict[str, dict[str, float]],
    label_resolver: Callable[[str], str],
    top_n_movements: int = 3,
) -> tuple[
    float,
    float,
    float,
    float,
    list[ConcentracaoMovement],
    list[ConcentracaoMovement],
]:
    """HHI prior + current + top-3 share + top movements de share.

    HHI normalizado em [0, 10000] (shares em escala 0-100).
    Retorna (hhi_prior, hhi_current, top3_prior, top3_current, gainers, losers).
    """
    prior_total = sum(d["vop"] for d in prior_by_produto.values()) or 1e-9
    current_total = sum(d["vop"] for d in current_by_produto.values()) or 1e-9
    all_members = set(prior_by_produto.keys()) | set(current_by_produto.keys())

    movs: list[ConcentracaoMovement] = []
    hhi_prior = 0.0
    hhi_current = 0.0
    prior_shares: list[float] = []
    current_shares: list[float] = []
    for member_id in all_members:
        p_vop = prior_by_produto.get(member_id, {"vop": 0.0})["vop"]
        c_vop = current_by_produto.get(member_id, {"vop": 0.0})["vop"]
        p_share = p_vop / prior_total * 100
        c_share = c_vop / current_total * 100
        hhi_prior += p_share**2
        hhi_current += c_share**2
        prior_shares.append(p_share)
        current_shares.append(c_share)
        movs.append(
            ConcentracaoMovement(
                member_id=member_id,
                member_label=label_resolver(member_id),
                prior_share_pct=p_share,
                current_share_pct=c_share,
                delta_share_pp=c_share - p_share,
            )
        )
    prior_shares.sort(reverse=True)
    current_shares.sort(reverse=True)
    top3_prior = sum(prior_shares[:3])
    top3_current = sum(current_shares[:3])

    gainers_sorted = sorted(movs, key=lambda m: m.delta_share_pp, reverse=True)
    gainers = [m for m in gainers_sorted[:top_n_movements] if m.delta_share_pp > 0]
    losers_sorted = sorted(movs, key=lambda m: m.delta_share_pp)
    losers = [m for m in losers_sorted[:top_n_movements] if m.delta_share_pp < 0]

    return hhi_prior, hhi_current, top3_prior, top3_current, gainers, losers


def _project_close_aditivo(
    current_by_member: dict[str, float],
    du_decorridos: int,
    du_totais: int,
    label_resolver: Callable[[str], str],
    threshold_pct: float = _DRIVER_THRESHOLD_PCT,
    threshold_brl: float = _DRIVER_THRESHOLD_BRL,
) -> tuple[float, list[DriverContribution], DriverContribution | None]:
    """Projeta fechamento (linear) e decompoe parcela faltante por driver.

    factor = du_totais / du_decorridos. projected_i = current_i * factor.
    parcela_faltante_total = sum(projected) - sum(current).

    Drivers representam a contribuicao membro a membro a essa parcela.
    Retorna (projected_total, drivers, outros).
    """
    if du_decorridos <= 0 or du_totais <= 0:
        return 0.0, [], None
    factor = du_totais / du_decorridos
    projected = {m: v * factor for m, v in current_by_member.items()}
    projected_total = sum(projected.values())
    falta_total = projected_total - sum(current_by_member.values())
    abs_falta = abs(falta_total)
    threshold_abs = max(threshold_brl, threshold_pct * abs_falta)

    drivers: list[DriverContribution] = []
    outros_curr = 0.0
    outros_proj = 0.0
    for member_id, current_value in current_by_member.items():
        projected_value = projected[member_id]
        contrib = projected_value - current_value
        if abs(contrib) < threshold_abs:
            outros_curr += current_value
            outros_proj += projected_value
            continue
        drivers.append(
            DriverContribution(
                member_id=member_id,
                member_label=label_resolver(member_id),
                contribution_brl=contrib,
                contribution_pct=(contrib / abs_falta * 100) if abs_falta > 0 else None,
                prior_value=current_value,
                current_value=projected_value,
            )
        )
    drivers.sort(key=lambda d: abs(d.contribution_brl), reverse=True)
    outros: DriverContribution | None = None
    outros_contrib = outros_proj - outros_curr
    if outros_curr > 0 or outros_proj > 0:
        outros = DriverContribution(
            member_id="__outros__",
            member_label="Outros",
            contribution_brl=outros_contrib,
            contribution_pct=(outros_contrib / abs_falta * 100) if abs_falta > 0 else None,
            prior_value=outros_curr,
            current_value=outros_proj,
        )
    return projected_total, drivers, outros


def _build_narrative_pt_br(
    du_decorridos: int,
    du_totais_mes: int,
    du_disponivel: bool,
    vop: VarianceBridgeData,
    taxa: PvmBridgeData,
    prazo: PvmBridgeData,
    concentracao: ConcentracaoDeltaData,
    mes_anterior_label: str,
) -> str:
    """Frase pt-BR multi-KPI gerada server-side (template deterministico).

    Exemplo: "Em DU 8 de 21: VOP R$ 35,2 mi (+12,4%% vs abr/26), Taxa 2,38%%
    (-0,12pp), Prazo +1,5d, Top-3 +3,0pp. Cartao CDC e UA Sul movimentam mais."
    """
    if du_disponivel and du_totais_mes > 0:
        prefixo = f"Em DU {du_decorridos} de {du_totais_mes}: "
    else:
        prefixo = "MTD parcial: "

    # VOP
    vop_compact = _fmt_moeda_compacta_pt(vop.current_anchor_value)
    if vop.delta_pct is not None:
        sinal_v = "+" if vop.delta_pct >= 0 else ""
        vop_part = (
            f"VOP {vop_compact} ({sinal_v}{vop.delta_pct:.1f}% vs {mes_anterior_label})"
        ).replace(".", ",")
    else:
        vop_part = f"VOP {vop_compact}"

    # Taxa
    sinal_t = "+" if taxa.delta >= 0 else ""
    taxa_part = (
        f"Taxa {taxa.current_anchor_value:.2f}% ({sinal_t}{taxa.delta:.2f}pp)"
    ).replace(".", ",")

    # Prazo
    sinal_p = "+" if prazo.delta >= 0 else ""
    prazo_part = f"Prazo {sinal_p}{prazo.delta:.1f}d".replace(".", ",")

    parts = [vop_part, taxa_part, prazo_part]
    if abs(concentracao.delta_top_3_pp) >= 0.5:
        sinal_c = "+" if concentracao.delta_top_3_pp >= 0 else ""
        conc_part = (
            f"Top-3 {sinal_c}{concentracao.delta_top_3_pp:.1f}pp"
        ).replace(".", ",")
        parts.append(conc_part)

    base = f"{prefixo}{', '.join(parts)}."

    # Drivers de destaque (top 2 por |contribution_brl|)
    nomes_destaque: list[str] = []
    for d in vop.drivers[:2]:
        if d.member_label and d.member_label != "(n/d)":
            nomes_destaque.append(d.member_label)
    if nomes_destaque:
        if len(nomes_destaque) == 1:
            base += f" {nomes_destaque[0]} movimenta mais."
        else:
            base += f" {' e '.join(nomes_destaque[:2])} movimentam mais."

    return base


async def get_aba1_mes_corrente(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    dimension: str = "produto",
) -> tuple[AbaMesCorrenteData, Provenance]:
    """Bundle da Aba 0 — Mes corrente (variance decomposition).

    Decompoe o delta MTD vs DU equivalente do mes anterior em 6 KPIs:
        - VOP / Receita -> variance bridge aditiva + projecao linear
        - Taxa / Prazo  -> PVM bridge (Marshall-Edgeworth)
        - Mix produtos  -> dumbbell (top 7 produtos por |delta_share_pp|)
        - Concentracao  -> HHI delta + top movements

    `dimension` aplica-se a VOP, Receita, Taxa, Prazo. Mix e Concentracao
    sempre usam produto (independem do SegmentSwitch da UI).
    """
    if dimension not in ("produto", "ua", "faixa_ticket"):
        raise ValueError(f"Dimensao desconhecida: {dimension}")

    periodo_fim: date | None = filters.get("periodo_fim")
    today = periodo_fim or date.today()

    # 1. DU position
    du_disponivel, du_decorridos, du_totais = await _du_position(db, tenant_id, today)

    # 2. Janelas
    mes_inicio = today.replace(day=1)
    mes_corrente_filters = {
        **filters,
        "periodo_inicio": mes_inicio,
        "periodo_fim": today,
    }
    mes_corrente_label = f"{_MES_PT[today.month - 1]}/{today.year % 100:02d}"

    if du_disponivel and du_decorridos > 0:
        mes_ant_inicio, mes_ant_fim = await _mes_anterior_paridade_du(
            db, tenant_id, today, du_decorridos
        )
    else:
        mes_ant_inicio, mes_ant_fim = _mes_anterior_window(today)
    mes_anterior_label = (
        f"{_MES_PT[mes_ant_inicio.month - 1]}/{mes_ant_inicio.year % 100:02d}"
    )
    mes_anterior_filters = {
        **filters,
        "periodo_inicio": mes_ant_inicio,
        "periodo_fim": mes_ant_fim,
    }

    # 3. Aggregations por dimensao escolhida
    current_agg = await _agg_by_dimension(db, tenant_id, mes_corrente_filters, dimension)
    prior_agg = await _agg_by_dimension(db, tenant_id, mes_anterior_filters, dimension)

    # Mix e Concentracao sempre por produto
    if dimension == "produto":
        current_by_produto = current_agg
        prior_by_produto = prior_agg
    else:
        current_by_produto = await _agg_by_dimension(
            db, tenant_id, mes_corrente_filters, "produto"
        )
        prior_by_produto = await _agg_by_dimension(
            db, tenant_id, mes_anterior_filters, "produto"
        )

    # 4. Label resolvers
    if dimension == "produto":
        prod_nomes = await _produto_sigla_to_nome_map(db, tenant_id)

        def resolver(member_id: str) -> str:
            return prod_nomes.get(member_id, member_id)

    elif dimension == "ua":
        ua_nomes = await _ua_id_to_nome_map(db, tenant_id)

        def resolver(member_id: str) -> str:
            try:
                return ua_nomes.get(int(member_id), f"UA {member_id}")
            except (ValueError, TypeError):
                return f"UA {member_id}"

    else:  # faixa_ticket — member_id ja e label legivel

        def resolver(member_id: str) -> str:
            return member_id

    prod_nomes_for_mix = await _produto_sigla_to_nome_map(db, tenant_id)

    def produto_resolver(sigla: str) -> str:
        return prod_nomes_for_mix.get(sigla, sigla)

    # Threshold para "Outros" rollup: zerado para dimensoes low-cardinality
    # (produto/ua/faixa_ticket raramente passam de ~8 membros — todos cabem
    # no bridge sem agregar). Cedente (futuro, alta cardinalidade) usa
    # threshold padrao.
    _LOW_CARD_DIMS = ("produto", "ua", "faixa_ticket")
    aditiva_th_pct = 0.0 if dimension in _LOW_CARD_DIMS else _DRIVER_THRESHOLD_PCT
    aditiva_th_brl = 0.0 if dimension in _LOW_CARD_DIMS else _DRIVER_THRESHOLD_BRL

    # 5. VOP variance bridge
    vop_prior_total = sum(d["vop"] for d in prior_agg.values())
    vop_current_total = sum(d["vop"] for d in current_agg.values())
    vop_drivers, vop_outros, vop_delta = _decompose_variance_aditiva(
        {k: v["vop"] for k, v in prior_agg.items()},
        {k: v["vop"] for k, v in current_agg.items()},
        resolver,
        threshold_pct=aditiva_th_pct,
        threshold_brl=aditiva_th_brl,
    )
    # Anchor labels nao repetem o nome do KPI — ja vem no titulo do card.
    vop_data = VarianceBridgeData(
        prior_anchor_label=mes_anterior_label,
        prior_anchor_value=vop_prior_total,
        current_anchor_label=mes_corrente_label,
        current_anchor_value=vop_current_total,
        delta_brl=vop_delta,
        delta_pct=_safe_pct_change(vop_current_total, vop_prior_total)
        if vop_prior_total > 0
        else None,
        drivers=vop_drivers,
        outros_rollup=vop_outros,
    )

    # 6. VOP projecao
    vop_projecao: ProjectionBridgeData | None = None
    if du_disponivel and du_decorridos > 0 and du_decorridos < du_totais:
        proj_total, proj_drivers, proj_outros = _project_close_aditivo(
            {k: v["vop"] for k, v in current_agg.items()},
            du_decorridos,
            du_totais,
            resolver,
            threshold_pct=aditiva_th_pct,
            threshold_brl=aditiva_th_brl,
        )
        vop_projecao = ProjectionBridgeData(
            current_anchor_label=f"Atual (DU {du_decorridos})",
            current_anchor_value=vop_current_total,
            projected_close_label=f"Projecao {mes_corrente_label}",
            projected_close_value=proj_total,
            delta_brl=proj_total - vop_current_total,
            delta_pct=_safe_pct_change(proj_total, vop_current_total)
            if vop_current_total > 0
            else None,
            drivers=proj_drivers,
            outros_rollup=proj_outros,
        )

    # 7. Receita variance bridge
    receita_prior_total = sum(d["receita"] for d in prior_agg.values())
    receita_current_total = sum(d["receita"] for d in current_agg.values())
    receita_drivers, receita_outros, receita_delta = _decompose_variance_aditiva(
        {k: v["receita"] for k, v in prior_agg.items()},
        {k: v["receita"] for k, v in current_agg.items()},
        resolver,
        threshold_pct=aditiva_th_pct,
        threshold_brl=aditiva_th_brl,
    )
    receita_data = VarianceBridgeData(
        prior_anchor_label=mes_anterior_label,
        prior_anchor_value=receita_prior_total,
        current_anchor_label=mes_corrente_label,
        current_anchor_value=receita_current_total,
        delta_brl=receita_delta,
        delta_pct=_safe_pct_change(receita_current_total, receita_prior_total)
        if receita_prior_total > 0
        else None,
        drivers=receita_drivers,
        outros_rollup=receita_outros,
    )

    # 8. Receita projecao
    receita_projecao: ProjectionBridgeData | None = None
    if du_disponivel and du_decorridos > 0 and du_decorridos < du_totais:
        proj_total, proj_drivers, proj_outros = _project_close_aditivo(
            {k: v["receita"] for k, v in current_agg.items()},
            du_decorridos,
            du_totais,
            resolver,
            threshold_pct=aditiva_th_pct,
            threshold_brl=aditiva_th_brl,
        )
        receita_projecao = ProjectionBridgeData(
            current_anchor_label=f"Atual (DU {du_decorridos})",
            current_anchor_value=receita_current_total,
            projected_close_label=f"Projecao {mes_corrente_label}",
            projected_close_value=proj_total,
            delta_brl=proj_total - receita_current_total,
            delta_pct=_safe_pct_change(proj_total, receita_current_total)
            if receita_current_total > 0
            else None,
            drivers=proj_drivers,
            outros_rollup=proj_outros,
        )

    # 9. Taxa PVM
    taxa_prior_avg = (
        sum(d["taxa"] * d["vop"] for d in prior_agg.values())
        / (sum(d["vop"] for d in prior_agg.values()) or 1e-9)
    )
    taxa_current_avg = (
        sum(d["taxa"] * d["vop"] for d in current_agg.values())
        / (sum(d["vop"] for d in current_agg.values()) or 1e-9)
    )
    (
        taxa_mix,
        taxa_intra,
        taxa_top_mix,
        taxa_top_intra,
        taxa_outros_mix,
        taxa_outros_intra,
    ) = _decompose_pvm(
        prior_agg,
        current_agg,
        "taxa",
        resolver,
        threshold_unit=_PVM_THRESHOLD_TAXA_PP,
    )
    taxa_data = PvmBridgeData(
        prior_anchor_label=mes_anterior_label,
        prior_anchor_value=taxa_prior_avg,
        current_anchor_label=mes_corrente_label,
        current_anchor_value=taxa_current_avg,
        delta=taxa_current_avg - taxa_prior_avg,
        delta_unidade="pp",
        mix_effect=taxa_mix,
        intra_effect=taxa_intra,
        top_mix_contributors=taxa_top_mix,
        top_intra_contributors=taxa_top_intra,
        outros_mix_rollup=taxa_outros_mix,
        outros_intra_rollup=taxa_outros_intra,
    )

    # 10. Prazo PVM
    prazo_prior_avg = (
        sum(d["prazo"] * d["vop"] for d in prior_agg.values())
        / (sum(d["vop"] for d in prior_agg.values()) or 1e-9)
    )
    prazo_current_avg = (
        sum(d["prazo"] * d["vop"] for d in current_agg.values())
        / (sum(d["vop"] for d in current_agg.values()) or 1e-9)
    )
    (
        prazo_mix,
        prazo_intra,
        prazo_top_mix,
        prazo_top_intra,
        prazo_outros_mix,
        prazo_outros_intra,
    ) = _decompose_pvm(
        prior_agg,
        current_agg,
        "prazo",
        resolver,
        threshold_unit=_PVM_THRESHOLD_PRAZO_DIAS,
    )
    prazo_data = PvmBridgeData(
        prior_anchor_label=mes_anterior_label,
        prior_anchor_value=prazo_prior_avg,
        current_anchor_label=mes_corrente_label,
        current_anchor_value=prazo_current_avg,
        delta=prazo_current_avg - prazo_prior_avg,
        delta_unidade="dias",
        mix_effect=prazo_mix,
        intra_effect=prazo_intra,
        top_mix_contributors=prazo_top_mix,
        top_intra_contributors=prazo_top_intra,
        outros_mix_rollup=prazo_outros_mix,
        outros_intra_rollup=prazo_outros_intra,
    )

    # 11. Mix dumbbell
    mix_points = _build_dumbbell(
        prior_by_produto, current_by_produto, produto_resolver, top_n=7
    )
    mix_data = DumbbellSeriesData(
        prior_anchor_label=mes_anterior_label,
        current_anchor_label=mes_corrente_label,
        points=mix_points,
    )

    # 12. Concentracao HHI
    (
        hhi_prior,
        hhi_current,
        top3_prior,
        top3_current,
        gainers,
        losers,
    ) = _calcular_hhi_e_movements(
        prior_by_produto, current_by_produto, produto_resolver
    )
    concentracao_data = ConcentracaoDeltaData(
        dimension_label="Produto",
        prior_anchor_label=mes_anterior_label,
        current_anchor_label=mes_corrente_label,
        hhi_prior=hhi_prior,
        hhi_current=hhi_current,
        delta_hhi=hhi_current - hhi_prior,
        top_3_share_prior=top3_prior,
        top_3_share_current=top3_current,
        delta_top_3_pp=top3_current - top3_prior,
        movements_gainers=gainers,
        movements_losers=losers,
    )

    # 13. Narrative + comparacao label
    if du_disponivel and du_totais > 0:
        comparacao_label = (
            f"comparado a {mes_anterior_label} ate DU {du_decorridos} "
            f"(de {du_totais})"
        )
    else:
        comparacao_label = (
            f"comparado a {mes_anterior_label} (paridade de dia corrido)"
        )

    narrative = _build_narrative_pt_br(
        du_decorridos=du_decorridos,
        du_totais_mes=du_totais,
        du_disponivel=du_disponivel,
        vop=vop_data,
        taxa=taxa_data,
        prazo=prazo_data,
        concentracao=concentracao_data,
        mes_anterior_label=mes_anterior_label,
    )

    # 14. Serie diaria de VOP do mes corrente (alimenta card "VOP Diario").
    last_day = monthrange(today.year, today.month)[1]
    mes_fim_corrente = date(today.year, today.month, last_day)
    vop_diario = await _vop_diario_mes_corrente(
        db, tenant_id, filters, mes_inicio, mes_fim_corrente, today
    )

    data = AbaMesCorrenteData(
        narrative_sentence=narrative,
        comparacao_label_pt=comparacao_label,
        du_decorridos=du_decorridos,
        du_totais_mes=du_totais,
        du_disponivel=du_disponivel,
        vop=vop_data,
        vop_projecao=vop_projecao,
        receita=receita_data,
        receita_projecao=receita_projecao,
        taxa=taxa_data,
        prazo=prazo_data,
        mix=mix_data,
        concentracao=concentracao_data,
        vop_diario=vop_diario,
        dimension_active=dimension,
    )
    prov = await _build_provenance(db, tenant_id, filters)
    return data, prov


# ═══════════════════════════════════════════════════════════════════════════
# VOP Potencial = vop_realizado_mtd + caixa + liquidacoes_previstas
# ═══════════════════════════════════════════════════════════════════════════
#
# Definicao (CLAUDE.md §13, §14, e memoria `project_vop_projecao_cash_bounded`):
# o VOP que o fundo "ainda pode" gerar ate o fim do mes corrente, limitado
# pelo caixa disponivel + liquidacoes previstas a entrar.
#
# Janela: mes corrente (do dia 1 ate fim do mes calendario).
# - vop_realizado_mtd: SUM(Operacao.total_bruto) entre mes_inicio e hoje.
# - caixa: ultima snapshot de saldo livre por (UA, conta) — exclui escrow,
#   caucao e travada (flags estruturais do Bitfin via wh_caixa_snapshot).
# - liquidacoes_previstas: SUM(saldo_devedor) de titulos com situacao=0,
#   saldo>0, NOT sustado, vencimento entre hoje e mes_fim.
#
# Filtros do usuario:
# - `ua_id`: aplica a TUDO. Quando vazio, default e UAs com tipo IN (1, 2)
#   (FIDC + Securitizadora). Quando setado, respeita selecao explicita.
# - `produto_sigla`: aplica APENAS a vop_realizado_mtd. Caixa e liquidacoes
#   nao tem dimensao produto canonica.
# - `periodo_inicio` / `periodo_fim`: IGNORADOS — VOP Potencial e sempre
#   sobre o mes corrente. Outros filtros do usuario aplicam.


async def _resolve_uas_elegiveis(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id_filter: list[int] | None,
) -> list[tuple[int, str, int | None]]:
    """Retorna lista de (ua_id, ua_nome, ua_tipo) elegiveis para VOP Potencial.

    Default (ua_id_filter None ou vazio): UAs com `tipo IN (1, 2)` (FIDC +
    Securitizadora). Com filtro setado: respeita selecao do usuario AS-IS
    (incluindo `tipo=NULL` se o usuario quiser).
    """
    stmt = select(
        DimUnidadeAdministrativa.ua_id,
        DimUnidadeAdministrativa.nome,
        DimUnidadeAdministrativa.tipo,
    ).where(DimUnidadeAdministrativa.tenant_id == tenant_id)

    if ua_id_filter:
        stmt = stmt.where(DimUnidadeAdministrativa.ua_id.in_(ua_id_filter))
    else:
        stmt = stmt.where(DimUnidadeAdministrativa.tipo.in_([1, 2]))

    rows = (await db.execute(stmt)).all()
    return [(r.ua_id, r.nome, r.tipo) for r in rows]


async def _vop_realizado_mtd_por_ua(
    db: AsyncSession,
    tenant_id: UUID,
    base_filters: dict[str, Any],
    mes_inicio: date,
    hoje: date,
    ua_id_list: list[int],
) -> dict[int, float]:
    """SUM(Operacao.total_bruto) GROUP BY ua. Filtros via `_apply_filters`."""
    if not ua_id_list:
        return {}
    overridden = {
        **base_filters,
        "periodo_inicio": mes_inicio,
        "periodo_fim": hoje,
        "ua_id": ua_id_list,
    }
    stmt = _apply_filters(
        select(
            Operacao.unidade_administrativa_id,
            func.coalesce(func.sum(Operacao.total_bruto), 0),
        ).group_by(Operacao.unidade_administrativa_id),
        tenant_id=tenant_id,
        **overridden,
    )
    rows = (await db.execute(stmt)).all()
    return {int(ua_id): _as_float(total) for ua_id, total in rows}


async def _caixa_disponivel_por_ua(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id_list: list[int],
) -> dict[int, float]:
    """Soma de saldo livre por UA na ultima snapshot de cada conta.

    Sem filtro de produto (caixa nao tem dimensao produto). Filtro de UA
    aplicado via `ua_id IN (...)`.
    """
    if not ua_id_list:
        return {}
    # Subquery: ultima data_snapshot conhecida por conta_bancaria_id.
    latest_subq = (
        select(
            CaixaSnapshot.tenant_id.label("t"),
            CaixaSnapshot.conta_bancaria_id.label("cb"),
            func.max(CaixaSnapshot.data_snapshot).label("max_dt"),
        )
        .where(CaixaSnapshot.tenant_id == tenant_id)
        .group_by(CaixaSnapshot.tenant_id, CaixaSnapshot.conta_bancaria_id)
        .subquery()
    )
    stmt = (
        select(
            CaixaSnapshot.unidade_administrativa_id,
            func.coalesce(func.sum(CaixaSnapshot.saldo), 0),
        )
        .join(
            latest_subq,
            and_(
                CaixaSnapshot.tenant_id == latest_subq.c.t,
                CaixaSnapshot.conta_bancaria_id == latest_subq.c.cb,
                CaixaSnapshot.data_snapshot == latest_subq.c.max_dt,
            ),
        )
        .where(
            CaixaSnapshot.tenant_id == tenant_id,
            CaixaSnapshot.unidade_administrativa_id.in_(ua_id_list),
            CaixaSnapshot.ativa.is_(True),
            CaixaSnapshot.eh_escrow.is_(False),
            CaixaSnapshot.eh_caucao.is_(False),
            CaixaSnapshot.eh_travada.is_(False),
        )
        .group_by(CaixaSnapshot.unidade_administrativa_id)
    )
    rows = (await db.execute(stmt)).all()
    return {int(ua_id): _as_float(saldo) for ua_id, saldo in rows}


async def _liquidacoes_previstas_por_ua(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id_list: list[int],
    hoje: date,
    mes_fim: date,
) -> dict[int, float]:
    """SUM(Titulo.saldo_devedor) de titulos abertos vencendo ate fim do mes.

    `data_de_vencimento_efetiva` e DateTime — `cast(..., Date)` garante
    comparacao por dia. Sem filtro de produto (wh_titulo nao tem mapping
    canonico para produto sigla nesta versao).
    """
    if not ua_id_list:
        return {}
    stmt = (
        select(
            Titulo.unidade_administrativa_id,
            func.coalesce(func.sum(Titulo.saldo_devedor), 0),
        )
        .where(
            Titulo.tenant_id == tenant_id,
            Titulo.unidade_administrativa_id.in_(ua_id_list),
            Titulo.situacao == 0,
            Titulo.saldo_devedor > 0,
            Titulo.sustado_judicialmente.is_(False),
            cast(Titulo.data_de_vencimento_efetiva, Date) >= hoje,
            cast(Titulo.data_de_vencimento_efetiva, Date) <= mes_fim,
        )
        .group_by(Titulo.unidade_administrativa_id)
    )
    rows = (await db.execute(stmt)).all()
    return {int(ua_id): _as_float(saldo) for ua_id, saldo in rows}


async def get_vop_potencial(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
) -> tuple[VopPotencialData, Provenance]:
    """VOP Potencial -- consolidado e por UA do mes corrente.

    Janela do mes corrente derivada de `periodo_fim` quando setado (permite
    "viajar no tempo" pra recompor o calculo num mes passado), senao usa hoje.
    """
    periodo_fim = filters.get("periodo_fim")
    hoje = periodo_fim or date.today()
    mes_inicio = date(hoje.year, hoje.month, 1)
    last_day = monthrange(hoje.year, hoje.month)[1]
    mes_fim = date(hoje.year, hoje.month, last_day)

    # 1. Resolve UAs elegiveis
    ua_filter = filters.get("ua_id") or None
    uas = await _resolve_uas_elegiveis(db, tenant_id, ua_filter)
    ua_id_list = [u[0] for u in uas]
    ua_meta = {u[0]: (u[1], u[2]) for u in uas}

    # 2. Calcula 3 componentes em paralelo logico (sequencial e ok aqui;
    #    sao 3 queries simples sobre o gr_db local)
    vop_realizado = await _vop_realizado_mtd_por_ua(
        db, tenant_id, filters, mes_inicio, hoje, ua_id_list
    )
    caixa = await _caixa_disponivel_por_ua(db, tenant_id, ua_id_list)
    liquidacoes = await _liquidacoes_previstas_por_ua(
        db, tenant_id, ua_id_list, hoje, mes_fim
    )

    # 3. Monta linhas por UA (zera componente quando UA nao tem entry)
    por_ua: list[VopPotencialPorUa] = []
    total_vop_real = 0.0
    total_caixa = 0.0
    total_liq = 0.0
    for ua_id in ua_id_list:
        vr = vop_realizado.get(ua_id, 0.0)
        cx = caixa.get(ua_id, 0.0)
        lq = liquidacoes.get(ua_id, 0.0)
        vp = vr + cx + lq
        nome, tipo = ua_meta[ua_id]
        por_ua.append(
            VopPotencialPorUa(
                ua_id=ua_id,
                ua_nome=nome,
                ua_tipo=tipo,
                vop_realizado_mtd=vr,
                caixa_disponivel=cx,
                liquidacoes_previstas=lq,
                vop_potencial=vp,
            )
        )
        total_vop_real += vr
        total_caixa += cx
        total_liq += lq

    # Ordena: maior VOP Potencial primeiro
    por_ua.sort(key=lambda r: r.vop_potencial, reverse=True)

    data = VopPotencialData(
        mes_inicio=mes_inicio,
        mes_fim=mes_fim,
        hoje=hoje,
        vop_realizado_mtd=total_vop_real,
        caixa_disponivel=total_caixa,
        liquidacoes_previstas=total_liq,
        vop_potencial=total_vop_real + total_caixa + total_liq,
        por_ua=por_ua,
    )
    # Provenance ancorado em wh_operacao (proveniencia agregada multi-fonte
    # fica como follow-up; hoje usamos a do bitfin_adapter geral).
    prov = await _build_provenance(db, tenant_id, filters)
    return data, prov


# ═══════════════════════════════════════════════════════════════════════════
# Aba "Mes Corrente v3" — pagina /bi/operacoes3 (socio-diretor view)
# ═══════════════════════════════════════════════════════════════════════════


async def get_aba3_mes_corrente(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    dimension: str = "produto",
) -> tuple[AbaMesCorrenteV3Data, Provenance]:
    """Bundle da aba /bi/operacoes3 — Mes Corrente v3.

    Reusa `get_aba1_mes_corrente` (toda a decomposicao avancada — vop/receita/
    taxa/prazo/mix/concentracao + vop_diario) e adiciona:
      - termometro: 5 KPIs com dupla comparacao (VOP-DU + MOM-norm-DU)
      - Potencial: reusa `get_vop_potencial` consolidado
      - vop_diario_por_ua: serie diaria quebrada por UA (alimenta modo
        "Por UA" do hero L2 — stacked bar)

    `dimension` controla a decomposicao do VOP Waterfall (produto/ua/
    faixa_ticket) — alimenta o SegmentSwitch local do card no hero.
    """
    today = filters.get("periodo_fim") or date.today()

    # 1. Reuso da decomposicao v1 (vop, receita, taxa, prazo, mix, concentracao,
    #    vop_diario, du metadata). Dimensao propaga para o waterfall.
    v1_data, prov = await get_aba1_mes_corrente(
        db, tenant_id, filters, dimension=dimension
    )

    # 1b. VOP diario por UA — serie do filtro de UA do hero L2.
    mes_inicio = today.replace(day=1)
    last_day = monthrange(today.year, today.month)[1]
    mes_fim_corrente = date(today.year, today.month, last_day)
    vop_diario_por_ua = await _vop_diario_por_ua_mes_corrente(
        db, tenant_id, filters, mes_inicio, mes_fim_corrente, today
    )

    # 1c. VOP MTD + Δ VOP-DU por UA — alimenta header KPI quando uma UA
    # especifica e selecionada no card VOP Diario.
    if v1_data.du_disponivel and v1_data.du_decorridos > 0:
        mes_ant_par_inicio, mes_ant_par_fim = await _mes_anterior_paridade_du(
            db, tenant_id, today, v1_data.du_decorridos
        )
    else:
        mes_ant_par_inicio, mes_ant_par_fim = _mes_anterior_window(today)
    vop_mtd_por_ua = await _vop_mtd_por_ua(
        db,
        tenant_id,
        filters,
        mes_inicio,
        today,
        mes_ant_par_inicio,
        mes_ant_par_fim,
    )

    # 2. Termometro: 4 cells absolutos/medios.
    vop_cell, receita_cell, taxa_cell, prazo_cell = await _calcular_termometro_cells(
        db,
        tenant_id,
        filters,
        today,
        v1_data.du_decorridos,
        v1_data.du_disponivel,
    )

    # 3. Potencial: reusa get_vop_potencial (consolidado).
    pot_data, _ = await get_vop_potencial(db, tenant_id, filters)
    mes_label = f"{_MES_PT[today.month - 1]}/{today.year % 100:02d}"
    potencial_cell = MesCorrentePotencialCell(
        valor=pot_data.vop_potencial,
        realizado=pot_data.vop_realizado_mtd,
        caixa=pot_data.caixa_disponivel,
        a_liquidar=pot_data.liquidacoes_previstas,
        mes_label=mes_label,
    )

    termometro = MesCorrenteTermometro(
        vop=vop_cell,
        receita=receita_cell,
        taxa=taxa_cell,
        prazo=prazo_cell,
        potencial=potencial_cell,
    )

    data = AbaMesCorrenteV3Data(
        termometro=termometro,
        comparacao_label_pt=v1_data.comparacao_label_pt,
        du_decorridos=v1_data.du_decorridos,
        du_totais_mes=v1_data.du_totais_mes,
        du_disponivel=v1_data.du_disponivel,
        vop_diario=v1_data.vop_diario,
        vop_diario_por_ua=vop_diario_por_ua,
        vop_mtd_por_ua=vop_mtd_por_ua,
        vop=v1_data.vop,
        vop_projecao=v1_data.vop_projecao,
        receita=v1_data.receita,
        receita_projecao=v1_data.receita_projecao,
        taxa=v1_data.taxa,
        prazo=v1_data.prazo,
        mix=v1_data.mix,
        concentracao=v1_data.concentracao,
    )
    return data, prov


async def get_operacoes_do_dia(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    dia: date,
) -> tuple[OperacoesDoDiaData, Provenance]:
    """Drill 'operacoes do dia X' — conteudo do DrillDownSheet.

    Lista todas as operacoes efetivadas em `dia` (com filtros globais
    aplicados via `_apply_filters` §7.2), KPIs do dia e quebra por
    produto/UA.

    Cedente: le direto de `wh_operacao.cedente_nome`, populado pelo
    adapter Bitfin v2.1.0+ via cadeia `Operacao.ContaOperacionalId ->
    ContaOperacional.ClienteId -> Cliente.EntidadeId -> Entidade.Nome`.
    Modelo 1:1 — cada op tem um cedente unico. Antes deste fix o codigo
    fazia um lookup via `wh_operacao_item.titulo_id == wh_titulo_snapshot
    .snapshot_id` que era SEMANTICAMENTE ERRADO (espacos numericos
    diferentes — coincidencia trazia cedentes errados).

    Ops antigas pre-v2.1.0 podem ter `cedente_nome IS NULL` ate o
    Bitfin full_sync rodar. Quando NULL, exibimos None (frontend mostra "—").
    """
    op_data = cast(Operacao.data_de_efetivacao, Date)
    day_filters = {**filters, "periodo_inicio": dia, "periodo_fim": dia}

    # 1. Lista de operacoes do dia (cedente vem direto da tabela).
    stmt = _apply_filters(
        select(
            Operacao.id.label("op_id"),
            Operacao.data_de_efetivacao,
            Operacao.unidade_administrativa_id.label("ua_id"),
            _produto_expr().label("produto_sigla"),
            Operacao.total_bruto,
            Operacao.taxa_de_juros,
            Operacao.prazo_medio_real,
            Operacao.cedente_nome,
        )
        .where(op_data == dia)
        .order_by(Operacao.total_bruto.desc()),
        tenant_id=tenant_id,
        **day_filters,
    )
    rows = (await db.execute(stmt)).all()

    # 2. Resolvers para nomes (UA, produto)
    ua_nomes_map = await _ua_id_to_nome_map(db, tenant_id)
    produto_nomes_map = await _produto_sigla_to_nome_map(db, tenant_id)

    operacoes: list[OperacaoDoDiaItem] = []
    vop_total = 0.0
    por_produto: dict[str, float] = {}
    por_ua: dict[int, float] = {}

    for r in rows:
        valor = _as_float(r.total_bruto)
        vop_total += valor
        sigla = r.produto_sigla
        if sigla:
            por_produto[sigla] = por_produto.get(sigla, 0.0) + valor
        if r.ua_id is not None:
            por_ua[r.ua_id] = por_ua.get(r.ua_id, 0.0) + valor

        operacoes.append(
            OperacaoDoDiaItem(
                operacao_id=str(r.op_id),
                data_de_efetivacao=r.data_de_efetivacao.date()
                if hasattr(r.data_de_efetivacao, "date")
                else r.data_de_efetivacao,
                cedente=r.cedente_nome,
                produto_sigla=sigla,
                produto_nome=produto_nomes_map.get(sigla) if sigla else None,
                ua_id=r.ua_id,
                ua_nome=ua_nomes_map.get(r.ua_id) if r.ua_id is not None else None,
                valor_bruto=valor,
                taxa=_as_float(r.taxa_de_juros) if r.taxa_de_juros is not None else None,
                prazo_medio=_as_float(r.prazo_medio_real)
                if r.prazo_medio_real is not None
                else None,
            )
        )

    # 3. KPIs do dia (medias ponderadas por valor)
    n_ops = len(operacoes)
    ticket_medio = vop_total / n_ops if n_ops > 0 else 0.0
    taxa_media: float | None
    prazo_medio: float | None
    if vop_total > 0:
        soma_taxa = sum((o.taxa or 0.0) * o.valor_bruto for o in operacoes)
        soma_prazo = sum((o.prazo_medio or 0.0) * o.valor_bruto for o in operacoes)
        taxa_media = soma_taxa / vop_total
        prazo_medio = soma_prazo / vop_total
    else:
        taxa_media = None
        prazo_medio = None

    # 4. Quebras (ordenadas por valor desc, share calculado sobre vop_total)
    def _to_quebra(
        mapping: dict[Any, float], label_resolver: Callable[[Any], str]
    ) -> list[QuebraDiaPorDimensao]:
        out = [
            QuebraDiaPorDimensao(
                label=label_resolver(k),
                valor=v,
                share_pct=(v / vop_total * 100.0) if vop_total > 0 else 0.0,
            )
            for k, v in mapping.items()
        ]
        out.sort(key=lambda q: q.valor, reverse=True)
        return out

    por_produto_list = _to_quebra(
        por_produto, lambda s: produto_nomes_map.get(s, s) or s
    )
    por_ua_list = _to_quebra(
        por_ua, lambda i: ua_nomes_map.get(int(i), f"UA {i}")
    )

    data = OperacoesDoDiaData(
        data=dia,
        vop_do_dia=vop_total,
        n_operacoes=n_ops,
        ticket_medio=ticket_medio,
        taxa_media=taxa_media,
        prazo_medio=prazo_medio,
        operacoes=operacoes,
        por_produto=por_produto_list,
        por_ua=por_ua_list,
    )
    prov = await _build_provenance(db, tenant_id, filters)
    return data, prov


# ═══════════════════════════════════════════════════════════════════════════
# Tabela de cedentes MTD (alimenta a tabela narrativa em /bi/operacoes3 L3)
# ═══════════════════════════════════════════════════════════════════════════
#
# Granularidade: POR TITULO (correta). `wh_operacao_item.valor_base` carrega
# o valor bruto de cada titulo da operacao — e SUM(valor_base) = total_bruto
# da op (verificado em 2026-05-19, caso da op 9604: 204.467,69 = 204.467,69).
#
# A versao anterior atribuia o total_bruto inteiro ao "cedente principal"
# (MIN(nome)), o que causava super-atribuicao em ops com multiplos cedentes
# (caso real: op 9604 tinha 5 cedentes, e atribuiu R\$ 204k inteiros ao
# Agnus Seven que tinha apenas 1 de 12 titulos).


async def _titulos_por_cedente_periodo(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    periodo_inicio: date,
    periodo_fim: date,
) -> list[Any]:
    """Lista de ops do periodo agregadas por cedente.

    A partir do adapter bitfin v2.1.0 cada op tem 1 cedente unico
    (modelo 1:1 validado em 9269/9269 ops). Le `wh_operacao.cedente_nome`
    direto — antes esse codigo usava um lookup via OperacaoItem x
    TituloSnapshot que era SEMANTICAMENTE ERRADO (espacos numericos
    diferentes — coincidencia trazia cedentes errados na maioria das ops).

    Retorna lista de dicts com chaves: cedente_nome, cedente_id,
    valor_base, op_id, data_de_efetivacao, taxa. Nome `valor_base`
    mantido por compat com o caller `get_cedentes_mtd` — no modelo
    refatorado, valor_base = total_bruto da op (era a soma dos titulos
    que tinham aquele cedente; com 1 cedente por op, e o total inteiro).

    Aplica `_apply_filters` na consulta as ops do periodo.
    Ops com `cedente_nome IS NULL` (pre-v2.1.0, ate full_sync rodar)
    sao filtradas — frontend ja exibe "(n/d)" via fallback.
    """
    op_data = cast(Operacao.data_de_efetivacao, Date)
    win_filters = {**filters, "periodo_inicio": periodo_inicio, "periodo_fim": periodo_fim}

    stmt = _apply_filters(
        select(
            Operacao.operacao_id.label("op_id"),
            Operacao.data_de_efetivacao,
            Operacao.taxa_de_juros,
            Operacao.total_bruto,
            Operacao.cedente_id,
            Operacao.cedente_nome,
        )
        .where(
            and_(
                op_data.between(periodo_inicio, periodo_fim),
                Operacao.cedente_nome.is_not(None),
            )
        ),
        tenant_id=tenant_id,
        **win_filters,
    )
    rows = (await db.execute(stmt)).all()

    enriched: list[Any] = []
    for r in rows:
        if r.op_id is None:
            continue
        data_op = (
            r.data_de_efetivacao.date()
            if hasattr(r.data_de_efetivacao, "date")
            else r.data_de_efetivacao
        )
        taxa = _as_float(r.taxa_de_juros) if r.taxa_de_juros is not None else None
        enriched.append({
            "cedente_nome": r.cedente_nome,
            "cedente_id": r.cedente_id,
            "valor_base": _as_float(r.total_bruto) if r.total_bruto is not None else 0.0,
            "op_id": int(r.op_id),
            "data_de_efetivacao": data_op,
            "taxa": taxa,
        })
    return enriched


async def get_cedentes_mtd(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
) -> tuple[CedentesMtdData, Provenance]:
    """Tabela narrativa de cedentes MTD com status novo/recorrente/sumido.

    Calcula por cedente:
      - volume_mtd: SUM(total_bruto) das ops onde o cedente e principal no MTD
      - delta_vs_mes_ant_pct: % vs same-DU mes anterior
      - n_op, dias_mtd, taxa_media (ponderada por valor)
      - primeira_op / ultima_op (historicas)
      - status:
          'novo' = primeira_op historica cai dentro do MTD
          'sumido' = cedente apareceu no mes anterior MTD mas nao no MTD corrente
          'recorrente' = tinha ops antes do MTD E no MTD

    Sumidos: lookup adicional do mes anterior (same-DU); cedentes la presentes
    e ausentes do MTD entram com volume_mtd=None e delta=-100%.
    """
    periodo_fim = filters.get("periodo_fim")
    today = periodo_fim or date.today()
    mes_inicio = today.replace(day=1)
    mes_label = f"{_MES_PT[today.month - 1]}/{today.year % 100:02d}"

    # Janela same-DU mes anterior (apples-to-apples)
    du_disponivel, du_decorridos, _ = await _du_position(db, tenant_id, today)
    if du_disponivel and du_decorridos > 0:
        mes_ant_par_inicio, mes_ant_par_fim = await _mes_anterior_paridade_du(
            db, tenant_id, today, du_decorridos
        )
    else:
        mes_ant_par_inicio, mes_ant_par_fim = _mes_anterior_window(today)

    # 1. Titulos do MTD por cedente (granularidade real via valor_base)
    titulos_mtd = await _titulos_por_cedente_periodo(
        db, tenant_id, filters, mes_inicio, today
    )

    # 2. Titulos do mes anterior same-DU por cedente
    titulos_ant = await _titulos_por_cedente_periodo(
        db, tenant_id, filters, mes_ant_par_inicio, mes_ant_par_fim
    )

    # 3. Agrega MTD por cedente_nome (granularidade por titulo)
    mtd_agg: dict[str, dict[str, Any]] = {}
    for t in titulos_mtd:
        nome = t["cedente_nome"]
        entry = mtd_agg.setdefault(
            nome,
            {
                "cedente_id": t["cedente_id"],
                "volume": 0.0,
                "ops": set(),
                "dias": set(),
                "soma_taxa_x_valor": 0.0,
                "soma_valor": 0.0,
            },
        )
        entry["volume"] += t["valor_base"]
        entry["ops"].add(t["op_id"])
        entry["dias"].add(t["data_de_efetivacao"])
        if t["taxa"] is not None:
            entry["soma_taxa_x_valor"] += t["taxa"] * t["valor_base"]
            entry["soma_valor"] += t["valor_base"]

    # 4. Agrega mes anterior same-DU por cedente_nome (pra delta + detectar sumidos)
    ant_agg: dict[str, float] = {}
    for t in titulos_ant:
        ant_agg[t["cedente_nome"]] = ant_agg.get(t["cedente_nome"], 0.0) + t["valor_base"]

    # 5. Lookup historico (1a op + ultima op) para cedentes que aparecem em MTD ou ANT
    nomes_envolvidos = set(mtd_agg.keys()) | set(ant_agg.keys())
    historico: dict[str, tuple[date, date]] = {}
    if nomes_envolvidos:
        # Le cedente_nome direto de wh_operacao (populado pelo adapter bitfin
        # v2.1.0+). Modelo 1:1 — uma op tem um cedente.
        hist_stmt = (
            select(
                Operacao.cedente_nome,
                func.min(cast(Operacao.data_de_efetivacao, Date)).label("primeira"),
                func.max(cast(Operacao.data_de_efetivacao, Date)).label("ultima"),
            )
            .where(
                and_(
                    Operacao.tenant_id == tenant_id,
                    Operacao.efetivada.is_(True),
                    Operacao.data_de_efetivacao.is_not(None),
                    Operacao.cedente_nome.in_(list(nomes_envolvidos)),
                )
            )
            .group_by(Operacao.cedente_nome)
        )
        for r in (await db.execute(hist_stmt)).all():
            historico[r.cedente_nome] = (r.primeira, r.ultima)

    # 6. Monta linhas finais
    cedentes_out: list[CedenteMtdItem] = []
    for nome, m in mtd_agg.items():
        ant_val = ant_agg.get(nome, 0.0)
        if ant_val > 0:
            delta_pct: float | None = ((m["volume"] / ant_val) - 1.0) * 100.0
        else:
            delta_pct = None  # cedente sem base no mes ant (novo ou bridge)

        # Status: novo = primeira op historica esta dentro do MTD
        primeira, ultima = historico.get(nome, (None, None))
        if primeira is not None and primeira >= mes_inicio:
            status = "novo"
        else:
            status = "recorrente"

        taxa_media = (
            (m["soma_taxa_x_valor"] / m["soma_valor"])
            if m["soma_valor"] > 0
            else None
        )

        cedentes_out.append(
            CedenteMtdItem(
                cedente_nome=nome,
                cedente_id=m["cedente_id"],
                volume_mtd=m["volume"],
                delta_vs_mes_ant_pct=delta_pct,
                status=status,
                n_op=len(m["ops"]),
                dias_mtd=len(m["dias"]),
                taxa_media=taxa_media,
                primeira_op=primeira,
                ultima_op=ultima,
            )
        )

    # 7. Sumidos — cedentes que apareceram no mes ant mas zero no MTD
    sumidos = [nome for nome in ant_agg if nome not in mtd_agg]
    for nome in sumidos:
        primeira, ultima = historico.get(nome, (None, None))
        cedentes_out.append(
            CedenteMtdItem(
                cedente_nome=nome,
                cedente_id=None,
                volume_mtd=None,
                delta_vs_mes_ant_pct=-100.0,
                status="sumido",
                n_op=None,
                dias_mtd=None,
                taxa_media=None,
                primeira_op=primeira,
                ultima_op=ultima,
            )
        )

    # 8. Ordena: ativos primeiro (volume desc), sumidos por nome
    cedentes_out.sort(
        key=lambda c: (
            0 if c.volume_mtd is not None else 1,
            -(c.volume_mtd or 0.0),
            c.cedente_nome,
        )
    )

    data = CedentesMtdData(
        cedentes=cedentes_out,
        total=len(cedentes_out),
        mes_label=mes_label,
    )
    prov = await _build_provenance(db, tenant_id, filters)
    return data, prov
