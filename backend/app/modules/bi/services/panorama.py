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
    CondominioItem,
    PanoramaFilters,
    PanoramaKpis,
    PlPonto,
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
    where_all, params_all = _filter_where(f, include_competencia=False)
    serie_rows = (
        await db.execute(
            text(
                f"SELECT to_char(i.competencia, 'YYYY-MM') AS mes, "
                f"       sum(iv.tab_iv_a_vl_pl) AS pl, count(*) AS n "
                f"{_FROM} WHERE {where_all} "
                f"GROUP BY i.competencia ORDER BY i.competencia"
            ),
            params_all,
        )
    ).mappings().all()
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
