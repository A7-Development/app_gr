"""L2 Panorama — service da pagina `/bi/panorama` (Observatorio FIDC).

Mercado FIDC inteiro a partir do Informe Mensal CVM (schema federado
`cvm_remote.*` via postgres_fdw — CLAUDE.md 13.1). Dado PUBLICO, sem escopo
de tenant. Toda query de agregado passa por `_filter_where` (helper unico de
filtros globais — §7.2). Sem WHERE montado a mao em nenhum bundle.

Fase 1: `get_visao_geral` (KPIs + evolucao do PL + condominio + tamanho).

Nota metodologica fixada (auditoria 2026-06-01): so campos ESTRUTURADOS da
CVM entram aqui; nada de regex em denom_social. O indice de liquidez usa a
definicao "ampla" (Disp + tit publicos + compromissadas + CDB + cotas
555/FIF + outros RF), validada em conversa.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bi.schemas.common import Provenance
from app.modules.bi.schemas.panorama import (
    AdminRankingItem,
    CondominioItem,
    FundoComparativoData,
    FundoMetricaComparada,
    LastroPrazoData,
    LiquidezCell,
    LiquidezSeriePonto,
    PanoramaFilters,
    PanoramaKpis,
    PlayersData,
    PlPonto,
    PrazoFaixa,
    RiscoLiquidezData,
    TamanhoBucket,
    VisaoGeralData,
)

# Proveniencia — fonte publica federada (CLAUDE.md 13.1).
_SOURCE_TYPE = "public:cvm_fidc"
_ADAPTER_VERSION = "etl-cvm"

# Numerador do indice de liquidez AMPLA: caixa + aplicacoes financeiras sem
# risco de credito. Exclui DC, valores mobiliarios e cotas de FIDC (exposicao).
_LIQ = (
    "(coalesce(i.tab_i1_vl_disp,0)"
    "+coalesce(i.tab_i2d_vl_titpub_fed,0)"
    "+coalesce(i.tab_i2f_vl_oper_comprom,0)"
    "+coalesce(i.tab_i2e_vl_cdb,0)"
    "+coalesce(i.tab_i2c5_vl_cota_fundo_icvm555,0)"
    "+coalesce(i.tab_i2c5_vl_cota_fif,0)"
    "+coalesce(i.tab_i2g_vl_outro_rf,0))"
)

# Cotas de OUTROS fundos / ativo — classifica "fundo de cotas" (feeder).
_COTAS = (
    "(coalesce(i.tab_i2h_vl_cota_fidc,0)"
    "+coalesce(i.tab_i2i_vl_cota_fidc_np,0)"
    "+coalesce(i.tab_i2c5_vl_cota_fundo_icvm555,0)"
    "+coalesce(i.tab_i2c5_vl_cota_fif,0))"
)

# Faixas de porte (R$). (limite_inferior_inclusive, limite_superior_exclusive).
_FAIXA_PL: dict[str, tuple[float | None, float | None]] = {
    "lt50": (None, 50e6),
    "50_200": (50e6, 200e6),
    "200_500": (200e6, 500e6),
    "500_1000": (500e6, 1000e6),
    "gt1000": (1000e6, None),
}

# Join canonico tab_i (perfil/ativo) + tab_iv (PL). Reutilizado por todos os
# bundles para garantir mesma granularidade de filtro.
_FROM = (
    "FROM cvm_remote.tab_i i "
    "JOIN cvm_remote.tab_iv iv "
    "  ON iv.competencia = i.competencia "
    " AND iv.cnpj_fundo_classe = i.cnpj_fundo_classe"
)


def _filter_where(f: PanoramaFilters, *, include_competencia: bool) -> tuple[str, dict[str, Any]]:
    """Constroi o WHERE dos filtros globais + os bind params (§7.2).

    `include_competencia=True` fixa a competencia (agregados pontuais);
    `False` deixa a janela aberta (series temporais que iteram os 28 meses).
    Assume o alias `i` (tab_i) + `iv` (tab_iv) do `_FROM`.

    Fragmentos sao literais controlados pelo servidor (faixa/tipo) ou bind
    params (condom/admin) — nada de string livre do usuario no SQL.
    """
    clauses = ["iv.tab_iv_a_vl_pl > 0"]
    params: dict[str, Any] = {}

    if include_competencia:
        clauses.append("i.competencia = :comp")

    if f.condom in ("aberto", "fechado"):
        clauses.append("lower(i.condom) = :condom")
        params["condom"] = f.condom

    if f.admin_cnpj:
        clauses.append("i.cnpj_admin = :admin_cnpj")
        params["admin_cnpj"] = f.admin_cnpj

    if f.faixa_pl in _FAIXA_PL:
        lo, hi = _FAIXA_PL[f.faixa_pl]
        if lo is not None:
            clauses.append("iv.tab_iv_a_vl_pl >= :pl_min")
            params["pl_min"] = lo
        if hi is not None:
            clauses.append("iv.tab_iv_a_vl_pl < :pl_max")
            params["pl_max"] = hi

    if f.tipo_carteira == "cotas":
        clauses.append(f"{_COTAS} / nullif(i.tab_i_vl_ativo, 0) > 0.5")
    elif f.tipo_carteira == "propria":
        clauses.append(f"coalesce({_COTAS} / nullif(i.tab_i_vl_ativo, 0), 0) <= 0.5")

    return " AND ".join(clauses), params


def _needs_tab_i_join(f: PanoramaFilters) -> bool:
    """True se algum filtro exige a tabela tab_i (condom/admin/tipo de carteira).

    `faixa_pl` atua sobre `tab_iv_a_vl_pl` (em tab_iv), entao NAO exige o join.
    Usado para evitar o cross-join FDW patologico em series de 28 meses: sem
    filtro de tab_i, o planner do postgres_fdw puxa as duas foreign tables
    inteiras e junta local (~86s); a serie de PL so precisa de tab_iv, que
    agrega remotamente em ~80ms.
    """
    return bool(f.condom or f.admin_cnpj or f.tipo_carteira)


def _serie_where_tab_iv(f: PanoramaFilters) -> tuple[str, dict[str, Any]]:
    """WHERE da serie sobre tab_iv sozinha (quando nao ha filtro de tab_i)."""
    clauses = ["tab_iv_a_vl_pl > 0"]
    params: dict[str, Any] = {}
    if f.faixa_pl in _FAIXA_PL:
        lo, hi = _FAIXA_PL[f.faixa_pl]
        if lo is not None:
            clauses.append("tab_iv_a_vl_pl >= :pl_min")
            params["pl_min"] = lo
        if hi is not None:
            clauses.append("tab_iv_a_vl_pl < :pl_max")
            params["pl_max"] = hi
    return " AND ".join(clauses), params


def _prev_month(d: date) -> date:
    """Primeiro dia do mes anterior."""
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)


async def _resolve_competencia(db: AsyncSession, comp_str: str | None) -> date:
    """Resolve a competencia alvo (parse 'YYYY-MM' ou ultima disponivel)."""
    if comp_str:
        year, month = comp_str.split("-")
        return date(int(year), int(month), 1)
    row = await db.execute(text("SELECT max(competencia) FROM cvm_remote.tab_iv"))
    return row.scalar_one()


def _build_provenance(competencia: date, row_count: int) -> Provenance:
    return Provenance(
        source_type=_SOURCE_TYPE,
        source_ids=["cvm_remote.tab_i", "cvm_remote.tab_iv"],
        last_source_updated_at=datetime(competencia.year, competencia.month, competencia.day),
        trust_level="high",
        ingested_by_version=_ADAPTER_VERSION,
        row_count=row_count,
    )


async def get_visao_geral(
    db: AsyncSession, f: PanoramaFilters
) -> tuple[VisaoGeralData, Provenance]:
    """Aba Visao Geral: KPIs macro + evolucao do PL + condominio + tamanho."""
    comp = await _resolve_competencia(db, f.competencia)
    where_c, params = _filter_where(f, include_competencia=True)
    params = {**params, "comp": comp}

    # 1. KPIs base (n, PL, liquidez) na competencia alvo.
    krow = (
        await db.execute(
            text(
                f"SELECT count(*) AS n, "
                f"       coalesce(sum(iv.tab_iv_a_vl_pl), 0) AS pl, "
                f"       coalesce(sum({_LIQ}), 0) AS liq "
                f"{_FROM} WHERE {where_c}"
            ),
            params,
        )
    ).mappings().one()
    n_fidc = int(krow["n"])
    pl_total = float(krow["pl"])
    liq = float(krow["liq"])
    pl_medio = pl_total / n_fidc if n_fidc else 0.0
    liquidez_pct = 100.0 * liq / pl_total if pl_total else 0.0

    # 2. delta de fundos vs competencia anterior (mesmos filtros).
    prev_params = {**params, "comp": _prev_month(comp)}
    prev_n = (
        await db.execute(
            text(f"SELECT count(*) AS n {_FROM} WHERE {where_c}"), prev_params
        )
    ).scalar_one()
    delta_fundos = n_fidc - int(prev_n)

    # 3. Evolucao do PL — serie mensal (janela aberta, filtros aplicados por mes).
    # Sem filtro de tab_i: tab_iv sozinha (agrega remoto, ~80ms). Com filtro de
    # tab_i: join (rapido — o filtro empurra pro remoto). Ver _needs_tab_i_join.
    if _needs_tab_i_join(f):
        where_all, params_all = _filter_where(f, include_competencia=False)
        serie_sql = (
            f"SELECT to_char(i.competencia, 'YYYY-MM') AS mes, "
            f"       sum(iv.tab_iv_a_vl_pl) AS pl, count(*) AS n "
            f"{_FROM} WHERE {where_all} "
            f"GROUP BY i.competencia ORDER BY i.competencia"
        )
    else:
        where_iv, params_all = _serie_where_tab_iv(f)
        serie_sql = (
            f"SELECT to_char(competencia, 'YYYY-MM') AS mes, "
            f"       sum(tab_iv_a_vl_pl) AS pl, count(*) AS n "
            f"FROM cvm_remote.tab_iv WHERE {where_iv} "
            f"GROUP BY competencia ORDER BY competencia"
        )
    serie_rows = (await db.execute(text(serie_sql), params_all)).mappings().all()
    evolucao_pl = [
        PlPonto(competencia=str(r["mes"]), pl=float(r["pl"] or 0), n_fidc=int(r["n"]))
        for r in serie_rows
    ]

    # 4. Split por condominio.
    cond_rows = (
        await db.execute(
            text(
                f"SELECT initcap(lower(i.condom)) AS condom, count(*) AS n, "
                f"       sum(iv.tab_iv_a_vl_pl) AS pl "
                f"{_FROM} WHERE {where_c} "
                f"GROUP BY initcap(lower(i.condom)) ORDER BY pl DESC"
            ),
            params,
        )
    ).mappings().all()
    por_condominio = [
        CondominioItem(
            condom=str(r["condom"] or "—"),
            n_fidc=int(r["n"]),
            pl=float(r["pl"] or 0),
            pct_pl=round(100.0 * float(r["pl"] or 0) / pl_total, 2) if pl_total else 0.0,
        )
        for r in cond_rows
    ]

    # 5. Distribuicao de tamanho (faixa de PL).
    tam_rows = (
        await db.execute(
            text(
                f"SELECT faixa, ord, count(*) AS n, sum(pl) AS pl FROM ("
                f"  SELECT iv.tab_iv_a_vl_pl AS pl, "
                f"    CASE WHEN iv.tab_iv_a_vl_pl < 50e6 THEN 1 "
                f"         WHEN iv.tab_iv_a_vl_pl < 200e6 THEN 2 "
                f"         WHEN iv.tab_iv_a_vl_pl < 500e6 THEN 3 "
                f"         WHEN iv.tab_iv_a_vl_pl < 1000e6 THEN 4 ELSE 5 END AS ord, "
                f"    CASE WHEN iv.tab_iv_a_vl_pl < 50e6 THEN '< R$ 50 mi' "
                f"         WHEN iv.tab_iv_a_vl_pl < 200e6 THEN 'R$ 50-200 mi' "
                f"         WHEN iv.tab_iv_a_vl_pl < 500e6 THEN 'R$ 200-500 mi' "
                f"         WHEN iv.tab_iv_a_vl_pl < 1000e6 THEN 'R$ 500 mi-1 bi' "
                f"         ELSE '> R$ 1 bi' END AS faixa "
                f"  {_FROM} WHERE {where_c}"
                f") t GROUP BY faixa, ord ORDER BY ord"
            ),
            params,
        )
    ).mappings().all()
    distribuicao_tamanho = [
        TamanhoBucket(faixa=str(r["faixa"]), n_fidc=int(r["n"]), pl=float(r["pl"] or 0))
        for r in tam_rows
    ]

    data = VisaoGeralData(
        competencia=comp.strftime("%Y-%m"),
        kpis=PanoramaKpis(
            pl_total=pl_total,
            n_fidc=n_fidc,
            pl_medio=pl_medio,
            delta_fundos=delta_fundos,
            liquidez_pct=round(liquidez_pct, 2),
        ),
        evolucao_pl=evolucao_pl,
        por_condominio=por_condominio,
        distribuicao_tamanho=distribuicao_tamanho,
    )
    return data, _build_provenance(comp, n_fidc)


# ════════════════════════════════════════════════════════════════════════
# Aba Players — ranking de administradoras
# ════════════════════════════════════════════════════════════════════════

_RANKING_LIMIT = 25


async def get_players(db: AsyncSession, f: PanoramaFilters) -> tuple[PlayersData, Provenance]:
    """Ranking de administradoras: qtd, PL, PL medio/mediano, liquidez."""
    comp = await _resolve_competencia(db, f.competencia)
    where_c, params = _filter_where(f, include_competencia=True)
    params = {**params, "comp": comp}

    rows = (
        await db.execute(
            text(
                f"WITH base AS ("
                f"  SELECT i.cnpj_admin AS cnpj_admin, i.admin AS admin, "
                f"         iv.tab_iv_a_vl_pl AS pl, {_LIQ} AS liq "
                f"  {_FROM} WHERE {where_c}"
                f") "
                f"SELECT cnpj_admin, max(admin) AS admin, count(*) AS qtd, "
                f"       sum(pl) AS pl, avg(pl) AS pl_medio, "
                f"       percentile_cont(0.5) WITHIN GROUP (ORDER BY pl) AS pl_mediano, "
                f"       100.0 * sum(liq) / nullif(sum(pl), 0) AS liquidez_pct "
                f"FROM base GROUP BY cnpj_admin ORDER BY pl DESC NULLS LAST"
            ),
            params,
        )
    ).mappings().all()

    total_n = sum(int(r["qtd"]) for r in rows)
    total_pl = sum(float(r["pl"] or 0) for r in rows)
    ranking = [
        AdminRankingItem(
            cnpj_admin=str(r["cnpj_admin"] or "—"),
            admin=str(r["admin"] or "—"),
            qtd=int(r["qtd"]),
            pct_qtd=round(100.0 * int(r["qtd"]) / total_n, 2) if total_n else 0.0,
            pl=float(r["pl"] or 0),
            pct_pl=round(100.0 * float(r["pl"] or 0) / total_pl, 2) if total_pl else 0.0,
            pl_medio=float(r["pl_medio"] or 0),
            pl_mediano=float(r["pl_mediano"] or 0),
            liquidez_pct=round(float(r["liquidez_pct"] or 0), 2),
        )
        for r in rows[:_RANKING_LIMIT]
    ]
    data = PlayersData(
        competencia=comp.strftime("%Y-%m"),
        total_fidc=total_n,
        pl_total=total_pl,
        ranking=ranking,
    )
    return data, _build_provenance(comp, total_n)


# ════════════════════════════════════════════════════════════════════════
# Aba Lastro & Prazo — distribuicao da carteira a vencer por faixa
# ════════════════════════════════════════════════════════════════════════

# 10 faixas do informe (tab_v com risco + tab_vi sem risco). Faixa +1080d e
# ABERTA — por isso reportamos distribuicao, nunca prazo medio em dias.
_PRAZO_FAIXAS: list[tuple[str, str, str]] = [
    ("ate 30d", "tab_v_a1_vl_prazo_venc_30", "tab_vi_a1_vl_prazo_venc_30"),
    ("31-60d", "tab_v_a2_vl_prazo_venc_60", "tab_vi_a2_vl_prazo_venc_60"),
    ("61-90d", "tab_v_a3_vl_prazo_venc_90", "tab_vi_a3_vl_prazo_venc_90"),
    ("91-120d", "tab_v_a4_vl_prazo_venc_120", "tab_vi_a4_vl_prazo_venc_120"),
    ("121-150d", "tab_v_a5_vl_prazo_venc_150", "tab_vi_a5_vl_prazo_venc_150"),
    ("151-180d", "tab_v_a6_vl_prazo_venc_180", "tab_vi_a6_vl_prazo_venc_180"),
    ("181-360d", "tab_v_a7_vl_prazo_venc_360", "tab_vi_a7_vl_prazo_venc_360"),
    ("361-720d", "tab_v_a8_vl_prazo_venc_720", "tab_vi_a8_vl_prazo_venc_720"),
    ("721-1080d", "tab_v_a9_vl_prazo_venc_1080", "tab_vi_a9_vl_prazo_venc_1080"),
    ("+1080d", "tab_v_a10_vl_prazo_venc_maior_1080", "tab_vi_a10_vl_prazo_venc_maior_1080"),
]

# JOIN tab_v + tab_vi + tab_i + tab_iv (os dois ultimos para os filtros globais).
_FROM_PRAZO = (
    "FROM cvm_remote.tab_v v "
    "JOIN cvm_remote.tab_vi w ON w.competencia = v.competencia "
    "  AND w.cnpj_fundo_classe = v.cnpj_fundo_classe "
    "JOIN cvm_remote.tab_i i ON i.competencia = v.competencia "
    "  AND i.cnpj_fundo_classe = v.cnpj_fundo_classe "
    "JOIN cvm_remote.tab_iv iv ON iv.competencia = v.competencia "
    "  AND iv.cnpj_fundo_classe = v.cnpj_fundo_classe"
)


async def get_lastro_prazo(
    db: AsyncSession, f: PanoramaFilters
) -> tuple[LastroPrazoData, Provenance]:
    """Distribuicao da carteira a vencer por faixa de prazo (sem media)."""
    comp = await _resolve_competencia(db, f.competencia)
    where_c, params = _filter_where(f, include_competencia=True)
    params = {**params, "comp": comp}

    selects = ", ".join(
        f"sum(coalesce(v.{vcol},0)+coalesce(w.{wcol},0)) AS f{idx}"
        for idx, (_, vcol, wcol) in enumerate(_PRAZO_FAIXAS)
    )
    row = (
        await db.execute(
            text(f"SELECT {selects} {_FROM_PRAZO} WHERE {where_c}"), params
        )
    ).mappings().one()

    valores = [float(row[f"f{idx}"] or 0) for idx in range(len(_PRAZO_FAIXAS))]
    total = sum(valores)
    distribuicao = [
        PrazoFaixa(
            faixa=label,
            valor=valores[idx],
            pct=round(100.0 * valores[idx] / total, 1) if total else 0.0,
        )
        for idx, (label, _, _) in enumerate(_PRAZO_FAIXAS)
    ]
    data = LastroPrazoData(
        competencia=comp.strftime("%Y-%m"),
        total_a_vencer=total,
        distribuicao_prazo=distribuicao,
    )
    n = int((await db.execute(text(f"SELECT count(*) {_FROM} WHERE {where_c}"), params)).scalar_one())
    return data, _build_provenance(comp, n)


# ════════════════════════════════════════════════════════════════════════
# Aba Risco & Liquidez — matriz porte x condominio + serie do indice
# ════════════════════════════════════════════════════════════════════════

# Expressao de bucket de porte (rotulo + ordem) reutilizada na matriz.
_PORTE_CASE_ORD = (
    "CASE WHEN iv.tab_iv_a_vl_pl < 50e6 THEN 1 WHEN iv.tab_iv_a_vl_pl < 200e6 THEN 2 "
    "WHEN iv.tab_iv_a_vl_pl < 500e6 THEN 3 WHEN iv.tab_iv_a_vl_pl < 1000e6 THEN 4 ELSE 5 END"
)
_PORTE_CASE_LBL = (
    "CASE WHEN iv.tab_iv_a_vl_pl < 50e6 THEN '< R$ 50 mi' "
    "WHEN iv.tab_iv_a_vl_pl < 200e6 THEN 'R$ 50-200 mi' "
    "WHEN iv.tab_iv_a_vl_pl < 500e6 THEN 'R$ 200-500 mi' "
    "WHEN iv.tab_iv_a_vl_pl < 1000e6 THEN 'R$ 500 mi-1 bi' ELSE '> R$ 1 bi' END"
)


async def get_risco_liquidez(
    db: AsyncSession, f: PanoramaFilters
) -> tuple[RiscoLiquidezData, Provenance]:
    """Matriz porte x condominio do indice de liquidez + serie ponderado/mediano."""
    comp = await _resolve_competencia(db, f.competencia)
    where_c, params = _filter_where(f, include_competencia=True)
    params = {**params, "comp": comp}

    matriz_rows = (
        await db.execute(
            text(
                f"WITH f AS ("
                f"  SELECT initcap(lower(i.condom)) AS condom, iv.tab_iv_a_vl_pl AS pl, "
                f"         {_LIQ} AS liq, {_PORTE_CASE_ORD} AS ord, {_PORTE_CASE_LBL} AS porte "
                f"  {_FROM} WHERE {where_c}"
                f") "
                f"SELECT porte, ord, condom, "
                f"  100.0 * sum(liq) / nullif(sum(pl), 0) AS pond, "
                f"  100 * percentile_cont(0.5) WITHIN GROUP (ORDER BY liq / nullif(pl,0)) AS med, "
                f"  count(*) AS n "
                f"FROM f GROUP BY porte, ord, condom ORDER BY ord, condom"
            ),
            params,
        )
    ).mappings().all()
    matriz = [
        LiquidezCell(
            porte=str(r["porte"]),
            condom=str(r["condom"] or "—"),
            indice_ponderado=round(float(r["pond"] or 0), 2),
            mediana=round(float(r["med"] or 0), 2),
            n_fidc=int(r["n"]),
        )
        for r in matriz_rows
    ]

    # A serie cruza tab_i x tab_iv em 28 meses. Sem filtro seletivo, o
    # postgres_fdw (estimativas default) escolhe MERGE JOIN O(n^2) -> ~87s.
    # Forcar HASH JOIN local (O(n)) derruba pra ~2s. SET LOCAL = escopo da
    # transacao da request; nao vaza pro pool nem afeta queries ja executadas.
    await db.execute(text("SET LOCAL enable_mergejoin = off"))
    await db.execute(text("SET LOCAL enable_nestloop = off"))
    where_all, params_all = _filter_where(f, include_competencia=False)
    serie_rows = (
        await db.execute(
            text(
                f"WITH f AS ("
                f"  SELECT i.competencia AS competencia, iv.tab_iv_a_vl_pl AS pl, {_LIQ} AS liq "
                f"  {_FROM} WHERE {where_all}"
                f") "
                f"SELECT to_char(competencia, 'YYYY-MM') AS mes, "
                f"  100.0 * sum(liq) / nullif(sum(pl), 0) AS pond, "
                f"  100 * percentile_cont(0.5) WITHIN GROUP (ORDER BY liq / nullif(pl,0)) AS med "
                f"FROM f GROUP BY competencia ORDER BY competencia"
            ),
            params_all,
        )
    ).mappings().all()
    serie = [
        LiquidezSeriePonto(
            competencia=str(r["mes"]),
            indice_ponderado=round(float(r["pond"] or 0), 2),
            mediana=round(float(r["med"] or 0), 2),
        )
        for r in serie_rows
    ]

    n = sum(c.n_fidc for c in matriz)
    data = RiscoLiquidezData(competencia=comp.strftime("%Y-%m"), matriz=matriz, serie=serie)
    return data, _build_provenance(comp, n)


# ════════════════════════════════════════════════════════════════════════
# Aba REALINVEST vs Mercado — tear-sheet + percentis
# ════════════════════════════════════════════════════════════════════════

# Fundo "nosso" default. TODO: vir de config do tenant em vez de hardcode
# quando o cockpit A7-vs-mercado virar multi-tenant.
_FUNDO_PADRAO_CNPJ = "42.449.234/0001-60"

# Soma ponderada por ponto medio das faixas (dias) — prazo medio de UM fundo.
# Confiavel so para carteira curta (faixa +1080d aberta); REALINVEST e curtissimo.
_PRAZO_WSUM = (
    "15*(coalesce(v.tab_v_a1_vl_prazo_venc_30,0)+coalesce(w.tab_vi_a1_vl_prazo_venc_30,0))"
    "+45*(coalesce(v.tab_v_a2_vl_prazo_venc_60,0)+coalesce(w.tab_vi_a2_vl_prazo_venc_60,0))"
    "+75*(coalesce(v.tab_v_a3_vl_prazo_venc_90,0)+coalesce(w.tab_vi_a3_vl_prazo_venc_90,0))"
    "+105*(coalesce(v.tab_v_a4_vl_prazo_venc_120,0)+coalesce(w.tab_vi_a4_vl_prazo_venc_120,0))"
    "+135*(coalesce(v.tab_v_a5_vl_prazo_venc_150,0)+coalesce(w.tab_vi_a5_vl_prazo_venc_150,0))"
    "+165*(coalesce(v.tab_v_a6_vl_prazo_venc_180,0)+coalesce(w.tab_vi_a6_vl_prazo_venc_180,0))"
    "+270*(coalesce(v.tab_v_a7_vl_prazo_venc_360,0)+coalesce(w.tab_vi_a7_vl_prazo_venc_360,0))"
    "+540*(coalesce(v.tab_v_a8_vl_prazo_venc_720,0)+coalesce(w.tab_vi_a8_vl_prazo_venc_720,0))"
    "+900*(coalesce(v.tab_v_a9_vl_prazo_venc_1080,0)+coalesce(w.tab_vi_a9_vl_prazo_venc_1080,0))"
    "+1440*(coalesce(v.tab_v_a10_vl_prazo_venc_maior_1080,0)+coalesce(w.tab_vi_a10_vl_prazo_venc_maior_1080,0))"
)
_PRAZO_TOT = "(coalesce(v.tab_v_a_vl_dircred_prazo,0)+coalesce(w.tab_vi_a_vl_dircred_prazo,0))"


async def get_fundo_comparativo(
    db: AsyncSession, cnpj: str | None = None
) -> tuple[FundoComparativoData, Provenance]:
    """Tear-sheet de um fundo (default REALINVEST) posicionado vs o mercado."""
    cnpj = cnpj or _FUNDO_PADRAO_CNPJ
    comp = await _resolve_competencia(db, None)

    # 1. Perfil + PL + liquidez ratio + porte/condom do fundo.
    prof = (
        await db.execute(
            text(
                f"SELECT i.denom_social, i.condom, i.admin, iv.tab_iv_a_vl_pl AS pl, "
                f"  {_LIQ} AS liq, {_PORTE_CASE_ORD} AS porte_ord "
                f"{_FROM} WHERE i.competencia = :comp AND i.cnpj_fundo_classe = :cnpj"
            ),
            {"comp": comp, "cnpj": cnpj},
        )
    ).mappings().first()

    if prof is None:
        data = FundoComparativoData(
            competencia=comp.strftime("%Y-%m"), cnpj=cnpj, nome="(não encontrado)",
            condom=None, admin=None, pl=0.0, evolucao_pl=[], metricas=[], encontrado=False,
        )
        return data, _build_provenance(comp, 0)

    pl = float(prof["pl"] or 0)
    liq_ratio = (float(prof["liq"] or 0) / pl) if pl else 0.0
    porte_ord = int(prof["porte_ord"])
    condom = str(prof["condom"] or "").strip().lower() or None

    # 2. Prazo medio do fundo (dias).
    prazo_row = (
        await db.execute(
            text(
                f"SELECT {_PRAZO_WSUM} AS wsum, {_PRAZO_TOT} AS tot "
                f"FROM cvm_remote.tab_v v "
                f"JOIN cvm_remote.tab_vi w ON w.competencia=v.competencia AND w.cnpj_fundo_classe=v.cnpj_fundo_classe "
                f"WHERE v.competencia=:comp AND v.cnpj_fundo_classe=:cnpj"
            ),
            {"comp": comp, "cnpj": cnpj},
        )
    ).mappings().first()
    prazo_tot = float(prazo_row["tot"] or 0) if prazo_row else 0.0
    prazo_medio = (float(prazo_row["wsum"] or 0) / prazo_tot) if prazo_tot else 0.0

    # 3. Rating AA% (scr operacao) + inadimplencia (bucket com risco).
    rating_row = (
        await db.execute(
            text(
                "SELECT tab_x_scr_risco_oper_aa::numeric AS aa, "
                "(tab_x_scr_risco_oper_aa::numeric+tab_x_scr_risco_oper_a::numeric"
                "+tab_x_scr_risco_oper_b::numeric+tab_x_scr_risco_oper_c::numeric"
                "+tab_x_scr_risco_oper_d::numeric+tab_x_scr_risco_oper_e::numeric"
                "+tab_x_scr_risco_oper_f::numeric+tab_x_scr_risco_oper_g::numeric"
                "+tab_x_scr_risco_oper_h::numeric) AS tot "
                "FROM cvm_remote.tab_x WHERE competencia=:comp AND cnpj_fundo_classe=:cnpj"
            ),
            {"comp": comp, "cnpj": cnpj},
        )
    ).mappings().first()
    rating_aa = (
        100.0 * float(rating_row["aa"] or 0) / float(rating_row["tot"])
        if rating_row and float(rating_row["tot"] or 0) > 0
        else 0.0
    )
    inad_row = (
        await db.execute(
            text(
                "SELECT 100.0*tab_v_b_vl_dircred_inad/"
                "nullif(tab_v_a_vl_dircred_prazo+tab_v_b_vl_dircred_inad,0) AS inad "
                "FROM cvm_remote.tab_v WHERE competencia=:comp AND cnpj_fundo_classe=:cnpj"
            ),
            {"comp": comp, "cnpj": cnpj},
        )
    ).scalar()
    inad_pct = float(inad_row or 0)

    # 4. Serie do PL do fundo.
    serie_rows = (
        await db.execute(
            text(
                "SELECT to_char(competencia,'YYYY-MM') AS mes, tab_iv_a_vl_pl AS pl "
                "FROM cvm_remote.tab_iv WHERE cnpj_fundo_classe=:cnpj ORDER BY competencia"
            ),
            {"cnpj": cnpj},
        )
    ).mappings().all()
    evolucao_pl = [
        PlPonto(competencia=str(r["mes"]), pl=float(r["pl"] or 0), n_fidc=1)
        for r in serie_rows
    ]

    # 5. Percentis (liquidez + prazo) vs mercado e vs pares (mesmo condom+porte).
    liq_pct_mkt, liq_pct_peer, liq_med_mkt = await _percentil_liquidez(
        db, comp, liq_ratio, condom, porte_ord
    )
    prazo_pct_mkt, prazo_pct_peer, prazo_med_mkt = await _percentil_prazo(
        db, comp, prazo_medio, condom, porte_ord
    )

    metricas = [
        FundoMetricaComparada(label="PL", valor=pl, unidade="BRL"),
        FundoMetricaComparada(
            label="Prazo médio da carteira", valor=round(prazo_medio, 0), unidade="dias",
            mercado_mediana=prazo_med_mkt, percentil_mercado=prazo_pct_mkt,
            percentil_pares=prazo_pct_peer,
        ),
        FundoMetricaComparada(
            label="Liquidez / PL", valor=round(100 * liq_ratio, 2), unidade="%",
            mercado_mediana=liq_med_mkt, percentil_mercado=liq_pct_mkt,
            percentil_pares=liq_pct_peer,
        ),
        FundoMetricaComparada(label="Rating AA (operação)", valor=round(rating_aa, 1), unidade="%"),
        FundoMetricaComparada(label="Inadimplência", valor=round(inad_pct, 2), unidade="%"),
    ]
    data = FundoComparativoData(
        competencia=comp.strftime("%Y-%m"),
        cnpj=cnpj,
        nome=str(prof["denom_social"] or cnpj),
        condom=str(prof["condom"]) if prof["condom"] else None,
        admin=str(prof["admin"]) if prof["admin"] else None,
        pl=pl,
        evolucao_pl=evolucao_pl,
        metricas=metricas,
        encontrado=True,
    )
    return data, _build_provenance(comp, 1)


async def _percentil_liquidez(
    db: AsyncSession, comp: date, valor: float, condom: str | None, porte_ord: int
) -> tuple[float | None, float | None, float | None]:
    """Percentil do indice de liquidez do fundo vs mercado e vs pares + mediana mkt."""
    row = (
        await db.execute(
            text(
                f"WITH f AS ("
                f"  SELECT lower(i.condom) AS condom, {_PORTE_CASE_ORD} AS ord, "
                f"         {_LIQ}/nullif(iv.tab_iv_a_vl_pl,0) AS r "
                f"  {_FROM} WHERE i.competencia=:comp AND iv.tab_iv_a_vl_pl>0"
                f") "
                f"SELECT "
                f"  100.0*count(*) FILTER (WHERE r <= :v)/nullif(count(*),0) AS pct_mkt, "
                f"  100.0*count(*) FILTER (WHERE r <= :v AND condom=:condom AND ord=:ord)"
                f"    /nullif(count(*) FILTER (WHERE condom=:condom AND ord=:ord),0) AS pct_peer, "
                f"  100*percentile_cont(0.5) WITHIN GROUP (ORDER BY r) AS med_mkt "
                f"FROM f"
            ),
            {"comp": comp, "v": valor, "condom": condom, "ord": porte_ord},
        )
    ).mappings().one()
    return (
        _round_or_none(row["pct_mkt"]),
        _round_or_none(row["pct_peer"]),
        _round_or_none(row["med_mkt"]),
    )


async def _percentil_prazo(
    db: AsyncSession, comp: date, valor: float, condom: str | None, porte_ord: int
) -> tuple[float | None, float | None, float | None]:
    """Percentil do prazo medio do fundo vs mercado e vs pares + mediana mkt."""
    row = (
        await db.execute(
            text(
                f"WITH f AS ("
                f"  SELECT lower(i.condom) AS condom, {_PORTE_CASE_ORD} AS ord, "
                f"         ({_PRAZO_WSUM})/nullif({_PRAZO_TOT},0) AS pm "
                f"  {_FROM_PRAZO} WHERE v.competencia=:comp AND iv.tab_iv_a_vl_pl>0 "
                f"    AND {_PRAZO_TOT} > 0"
                f") "
                f"SELECT "
                f"  100.0*count(*) FILTER (WHERE pm <= :v)/nullif(count(*),0) AS pct_mkt, "
                f"  100.0*count(*) FILTER (WHERE pm <= :v AND condom=:condom AND ord=:ord)"
                f"    /nullif(count(*) FILTER (WHERE condom=:condom AND ord=:ord),0) AS pct_peer, "
                f"  percentile_cont(0.5) WITHIN GROUP (ORDER BY pm) AS med_mkt "
                f"FROM f"
            ),
            {"comp": comp, "v": valor, "condom": condom, "ord": porte_ord},
        )
    ).mappings().one()
    return (
        _round_or_none(row["pct_mkt"]),
        _round_or_none(row["pct_peer"]),
        _round_or_none(row["med_mkt"], 0),
    )


def _round_or_none(v: Any, ndigits: int = 1) -> float | None:
    return round(float(v), ndigits) if v is not None else None
