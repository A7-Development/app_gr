"""BI -> Benchmark: indicadores de benchmarking FIDC (cesta de 17).

Computa, por fundo x competencia, a cesta de indicadores definida em
`docs/cvm-fidc/indicadores-benchmarking.md`, com percentil de cada indicador
no universo da competencia + medianas de mercado. Toda a semantica dos campos
foi validada empiricamente — ver `docs/cvm-fidc/dicionario.md` (regras duras:
inadimplencia = tab_v + tab_vi sobre DC BRUTO; provisao armazenada positiva;
rentabilidade = tab_x_3, nunca delta-cota; SCR usa TODAS as letras; tab_ix
fora — nivel nao confiavel).

Fonte: schema federado `cvm_remote.*` (postgres_fdw, dado publico CVM FIDC).
Sem escopo de tenant (CLAUDE.md sec 13.1). Source type = 'public:cvm_fidc'.

REGRA DE PERFORMANCE (aprendida em prod 2026-06-11): NUNCA fazer JOIN entre
foreign tables nesta carga — sem estatisticas remotas o planner escolhe
nested-loop com query remota por linha e a consulta leva MINUTOS. Cada query
abaixo e um scan de UMA tabela filtrado por competencia (qual simples,
pushdown garantido, segundos); o merge e os indicadores sao computados em
Python (~4k fundos, trivial). Resultado cacheado em processo por competencia
(dado mensal estatico; CLAUDE.md sec 2 permite cache em-processo no MVP),
com lock p/ dedupe de calculo concorrente (warm-up + request).
"""

from __future__ import annotations

import asyncio
import bisect
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Pontos medios (dias) dos 10 buckets de prazo da tab_v/tab_vi.
_BUCKETS = (15, 45, 75, 105, 135, 165, 270, 540, 900, 1260)


def _q_buckets(t: str, prefixo: str) -> str:
    """Expressoes SQL dos 10 buckets a-vencer (soma ponderada p/ prazo medio)."""
    cols = [
        f"{prefixo}a1_vl_prazo_venc_30", f"{prefixo}a2_vl_prazo_venc_60",
        f"{prefixo}a3_vl_prazo_venc_90", f"{prefixo}a4_vl_prazo_venc_120",
        f"{prefixo}a5_vl_prazo_venc_150", f"{prefixo}a6_vl_prazo_venc_180",
        f"{prefixo}a7_vl_prazo_venc_360", f"{prefixo}a8_vl_prazo_venc_720",
        f"{prefixo}a9_vl_prazo_venc_1080", f"{prefixo}a10_vl_prazo_venc_maior_1080",
    ]
    wsum = " + ".join(
        f"COALESCE({c}, 0) * {m}" for c, m in zip(cols, _BUCKETS, strict=True)
    )
    inad90 = " + ".join(
        f"COALESCE({prefixo}{b}, 0)"
        for b in (
            "b4_vl_inad_120", "b5_vl_inad_150", "b6_vl_inad_180",
            "b7_vl_inad_360", "b8_vl_inad_720", "b9_vl_inad_1080",
            "b10_vl_inad_maior_1080",
        )
    )
    # >180d = faixas 181-360 / 361-720 / 721-1080 / >1080 (perda dura).
    inad180 = " + ".join(
        f"COALESCE({prefixo}{b}, 0)"
        for b in (
            "b7_vl_inad_360", "b8_vl_inad_720", "b9_vl_inad_1080",
            "b10_vl_inad_maior_1080",
        )
    )
    return f"""
        SELECT cnpj_fundo_classe AS cnpj,
            COALESCE({prefixo}a_vl_dircred_prazo, 0)::float AS av_total,
            COALESCE({prefixo}b_vl_dircred_inad, 0)::float AS inad,
            ({inad90})::float AS inad_90,
            ({inad180})::float AS inad_180,
            ({wsum})::float AS prazo_wsum
        FROM cvm_remote.{t}
        WHERE competencia = :comp
    """


_Q_I = text("""
    SELECT cnpj_fundo_classe AS cnpj,
        denom_social,
        INITCAP(LOWER(NULLIF(TRIM(condom), ''))) AS condominio,
        NULLIF(tab_i_vl_ativo, 0)::float AS ativo,
        (COALESCE(tab_i2a_vl_dircred_risco, 0)
          + COALESCE(tab_i2b_vl_dircred_sem_risco, 0))::float AS dc_liq,
        (COALESCE(tab_i2a11_vl_reducao_recup, 0)
          + COALESCE(tab_i2b11_vl_reducao_recup, 0))::float AS pdd,
        (COALESCE(tab_i1_vl_disp, 0)
          + COALESCE(tab_i2d_vl_titpub_fed, 0)
          + COALESCE(tab_i2e_vl_cdb, 0)
          + COALESCE(tab_i2f_vl_oper_comprom, 0)
          + COALESCE(tab_i2g_vl_outro_rf, 0)
          + COALESCE(tab_i2c5_vl_cota_fif, 0)
          + COALESCE(tab_i2c5_vl_cota_fundo_icvm555, 0)
          + COALESCE(tab_i4a_vl_cprazo, 0))::float AS alta_liquidez
    FROM cvm_remote.tab_i
    WHERE competencia = :comp
""")

_Q_II = text("""
    SELECT cnpj_fundo_classe AS cnpj, NULLIF(tab_ii_vl_carteira, 0)::float AS dc_bruto
    FROM cvm_remote.tab_ii
    WHERE competencia = :comp
""")

_Q_III = text("""
    SELECT cnpj_fundo_classe AS cnpj, COALESCE(tab_iii_vl_passivo, 0)::float AS passivo
    FROM cvm_remote.tab_iii
    WHERE competencia = :comp
""")

_Q_IV = text("""
    SELECT cnpj_fundo_classe AS cnpj,
        NULLIF(tab_iv_a_vl_pl, 0)::float AS pl,
        tab_iv_b_vl_pl_medio::float AS pl_medio
    FROM cvm_remote.tab_iv
    WHERE competencia = :comp
""")

_Q_V = text(_q_buckets("tab_v", "tab_v_"))
_Q_VI = text(_q_buckets("tab_vi", "tab_vi_"))

_Q_VII = text("""
    SELECT cnpj_fundo_classe AS cnpj,
        (COALESCE(tab_vii_a1_2_vl_dircred_risco, 0)
          + COALESCE(tab_vii_a2_2_vl_dircred_sem_risco, 0))::float AS aquisicoes,
        COALESCE(tab_vii_d_2_vl_recompra, 0)::float AS recompra,
        COALESCE(tab_vii_d_3_vl_contab_recompra, 0)::float AS recompra_contabil
    FROM cvm_remote.tab_vii
    WHERE competencia = :comp
""")

# SCR: colunas TEXT com string numerica. Eixo OPERACAO, todas as letras (a
# regua AA..H soma o DC bruto — validado; ha arrasto de devedor).
_Q_X = text("""
    SELECT cnpj_fundo_classe AS cnpj,
        COALESCE(NULLIF(TRIM(tab_x_debito_tribut), '')::numeric, 0)::float AS divida_ativa,
        (COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_aa), '')::numeric, 0)
          + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_a), '')::numeric, 0)
          + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_b), '')::numeric, 0)
          + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_c), '')::numeric, 0))::float AS scr_aa_c,
        (COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_d), '')::numeric, 0)
          + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_e), '')::numeric, 0)
          + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_f), '')::numeric, 0)
          + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_g), '')::numeric, 0)
          + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_h), '')::numeric, 0))::float AS scr_d_h
    FROM cvm_remote.tab_x
    WHERE competencia = :comp
""")

# Series (x_2 e x_3) buscadas SEPARADAS (sem join FDW) — merge por
# (cnpj, classe_serie) em Python.
_Q_X2 = text("""
    SELECT cnpj_fundo_classe AS cnpj, tab_x_classe_serie AS serie,
        (tab_x_qt_cota * tab_x_vl_cota)::float AS pl_serie
    FROM cvm_remote.tab_x_2
    WHERE competencia = :comp
      AND tab_x_qt_cota IS NOT NULL AND tab_x_vl_cota IS NOT NULL
""")

_Q_X3 = text("""
    SELECT cnpj_fundo_classe AS cnpj, tab_x_classe_serie AS serie,
        tab_x_vl_rentab_mes::float AS rentab
    FROM cvm_remote.tab_x_3
    WHERE competencia = :comp AND tab_x_vl_rentab_mes IS NOT NULL
""")

_Q_X4 = text("""
    SELECT cnpj_fundo_classe AS cnpj,
        SUM(CASE tab_x_tp_oper
              WHEN 'Captações no Mês' THEN COALESCE(tab_x_vl_total, 0)
              WHEN 'Resgates no Mês' THEN -COALESCE(tab_x_vl_total, 0)
              WHEN 'Amortizações' THEN -COALESCE(tab_x_vl_total, 0)
              ELSE 0 END)::float AS captacao_liq
    FROM cvm_remote.tab_x_4
    WHERE competencia = :comp
    GROUP BY 1
""")

_Q_X6 = text("""
    SELECT cnpj_fundo_classe AS cnpj,
        (AVG(tab_x_pr_desemp_real - tab_x_pr_desemp_esperado)
          FILTER (WHERE COALESCE(tab_x_pr_desemp_esperado, 0) > 0))::float
          AS atingimento_pp
    FROM cvm_remote.tab_x_6
    WHERE competencia = :comp
    GROUP BY 1
""")

_COMPETENCIAS_QUERY = text("""
    SELECT DISTINCT competencia FROM cvm_remote.tab_iv
    ORDER BY competencia DESC
    LIMIT :limit
""")


@dataclass
class IndicadoresUniverso:
    """Universo de uma competencia: linhas por fundo (dicts) + medianas."""

    competencia: date
    fundos: dict[str, dict]  # cnpj -> row dict (indicadores + percentis)
    medianas: dict[str, float | None]
    total_fundos: int


# Indicadores que ganham percentil. Direcao: True = maior e melhor (orienta
# realce/radar no front). O percentil cru e SEMPRE "fracao do universo abaixo
# de mim" (ascendente).
INDICADOR_DIRECAO: dict[str, bool] = {
    "pl": True,
    "subordinacao_pct": True,
    "subordinacao_jr_pct": True,
    "sub_jr_sobre_sub_pct": True,
    "passivo_ativo_pct": False,
    "dc_ativo_pct": True,
    "alta_liquidez_pl_pct": True,
    "prazo_medio_dias": False,
    "inad_total_pct": False,
    "inad_90_pct": False,
    "inad_180_pct": False,
    "cobertura_pdd_pct": True,
    "pdd_pl_pct": False,
    "recompra_dc_pct": False,
    "captacao_liq_pl_pct": True,
    "giro_pct": True,
    "rentab_sub_pct": True,
    "atingimento_pp": True,
    "scr_dh_pct": False,
    "yield_efetivo_pct": True,
    "divida_ativa_pct": False,
}

# Cache em-processo por competencia (dado mensal estatico; MVP — CLAUDE.md §2)
# + lock p/ dedupe de calculo concorrente.
_cache: dict[date, IndicadoresUniverso] = {}
_cache_lock = asyncio.Lock()


def _ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return 100.0 * num / den


def _eh_sub_pura(serie: str | None) -> bool:
    s = (serie or "").lower()
    return "subord" in s and "mezanino" not in s


def _montar_fundos(dados: dict[str, list[dict]]) -> list[dict]:
    """Merge por cnpj + formulas da cesta (espelha o SQL antigo, validado)."""
    por = {nome: {r["cnpj"]: r for r in rows} for nome, rows in dados.items()
           if nome not in ("x2", "x3")}

    # Series: PL por (cnpj, serie) + rentab por (cnpj, serie).
    pl_serie: dict[tuple[str, str], float] = {}
    pl_subord: dict[str, float] = defaultdict(float)
    pl_sub_jr: dict[str, float] = defaultdict(float)
    pl_classes: dict[str, float] = defaultdict(float)
    for r in dados["x2"]:
        chave = (r["cnpj"], r["serie"])
        pl_serie[chave] = pl_serie.get(chave, 0.0) + (r["pl_serie"] or 0.0)
        pl_classes[r["cnpj"]] += r["pl_serie"] or 0.0
        if "subord" in (r["serie"] or "").lower():
            pl_subord[r["cnpj"]] += r["pl_serie"] or 0.0
        if _eh_sub_pura(r["serie"]):
            pl_sub_jr[r["cnpj"]] += r["pl_serie"] or 0.0
    resultado_mes: dict[str, float] = defaultdict(float)
    rentab_sub_wsum: dict[str, float] = defaultdict(float)
    pl_sub_puro: dict[str, float] = defaultdict(float)
    for r in dados["x3"]:
        pl_da_serie = pl_serie.get((r["cnpj"], r["serie"]))
        if pl_da_serie is None:
            continue
        resultado_mes[r["cnpj"]] += pl_da_serie * r["rentab"] / 100.0
        if _eh_sub_pura(r["serie"]):
            rentab_sub_wsum[r["cnpj"]] += pl_da_serie * r["rentab"]
            pl_sub_puro[r["cnpj"]] += pl_da_serie

    fundos: list[dict] = []
    for cnpj, i in por["i"].items():
        iv = por["iv"].get(cnpj) or {}
        pl = iv.get("pl")
        if pl is None or pl <= 0:
            continue  # universo = fundos com PL > 0 (mesmo filtro do SQL antigo)
        ii = por["ii"].get(cnpj) or {}
        ii_prev = por["ii_prev"].get(cnpj) or {}
        iii = por["iii"].get(cnpj) or {}
        v = por["v"].get(cnpj) or {}
        vi = por["vi"].get(cnpj) or {}
        vii = por["vii"].get(cnpj) or {}
        x = por["x"].get(cnpj) or {}
        x4 = por["x4"].get(cnpj) or {}
        x6 = por["x6"].get(cnpj) or {}

        dc_bruto = ii.get("dc_bruto")
        av_total = (v.get("av_total") or 0.0) + (vi.get("av_total") or 0.0)
        inad = (v.get("inad") or 0.0) + (vi.get("inad") or 0.0)
        inad_90 = (v.get("inad_90") or 0.0) + (vi.get("inad_90") or 0.0)
        inad_180 = (v.get("inad_180") or 0.0) + (vi.get("inad_180") or 0.0)
        prazo_wsum = (v.get("prazo_wsum") or 0.0) + (vi.get("prazo_wsum") or 0.0)
        sub = pl_subord.get(cnpj)
        sub_jr = pl_sub_jr.get(cnpj)
        spuro = pl_sub_puro.get(cnpj, 0.0)
        dc_medio = (
            (dc_bruto + (ii_prev.get("dc_bruto_prev") or dc_bruto)) / 2
            if dc_bruto is not None
            else None
        )

        fundos.append({
            "cnpj": cnpj,
            "denom_social": i.get("denom_social"),
            "condominio": i.get("condominio"),
            "pl": pl,
            "pl_medio": iv.get("pl_medio"),
            "subordinacao_pct": _ratio(sub, pl),
            # Por tranche: Jr/PL = protecao da mezanino (first-loss real);
            # Jr/Sub total = qualidade do colchao (100% quando nao ha mez).
            "subordinacao_jr_pct": _ratio(sub_jr, pl),
            "sub_jr_sobre_sub_pct": _ratio(sub_jr, sub),
            "passivo_ativo_pct": _ratio(iii.get("passivo"), i.get("ativo")),
            "dc_ativo_pct": _ratio(i.get("dc_liq"), i.get("ativo")),
            "alta_liquidez_pl_pct": _ratio(i.get("alta_liquidez"), pl),
            "prazo_medio_dias": prazo_wsum / av_total if av_total > 0 else None,
            "inad_total_pct": _ratio(inad, dc_bruto),
            "inad_90_pct": _ratio(inad_90, dc_bruto),
            "inad_180_pct": _ratio(inad_180, dc_bruto),
            "cobertura_pdd_pct": _ratio(i.get("pdd"), inad) if inad > 0 else None,
            "pdd_pl_pct": _ratio(i.get("pdd"), pl),
            "recompra_dc_pct": _ratio(vii.get("recompra") or 0.0, dc_bruto),
            "desagio_recompra": (vii.get("recompra_contabil") or 0.0)
                - (vii.get("recompra") or 0.0),
            "captacao_liq_pl_pct": _ratio(x4.get("captacao_liq") or 0.0, pl),
            "giro_pct": _ratio(vii.get("aquisicoes") or 0.0, dc_bruto),
            "rentab_sub_pct": (
                rentab_sub_wsum[cnpj] / spuro if spuro > 0 else None
            ),
            "atingimento_pp": x6.get("atingimento_pp"),
            "scr_dh_pct": _ratio(
                x.get("scr_d_h"),
                (x.get("scr_aa_c") or 0.0) + (x.get("scr_d_h") or 0.0) or None,
            ),
            "yield_efetivo_pct": _ratio(resultado_mes.get(cnpj), dc_medio),
            "divida_ativa_pct": _ratio(x.get("divida_ativa") or 0.0, dc_bruto),
        })
    return fundos


def _percentis_e_medianas(rows: list[dict]) -> dict[str, float | None]:
    """Anota `<indicador>_rank` (0-100, fracao do universo ESTRITAMENTE abaixo)
    em cada row, in place, e retorna as medianas do universo."""
    medianas: dict[str, float | None] = {}
    for campo in INDICADOR_DIRECAO:
        valores = sorted(r[campo] for r in rows if r.get(campo) is not None)
        n = len(valores)
        if n == 0:
            medianas[campo] = None
            continue
        medianas[campo] = (
            valores[n // 2]
            if n % 2 == 1
            else (valores[n // 2 - 1] + valores[n // 2]) / 2
        )
        for r in rows:
            valor = r.get(campo)
            r[f"{campo}_rank"] = (
                round(100 * bisect.bisect_left(valores, valor) / n, 1)
                if valor is not None and n > 1
                else None
            )
    return medianas


async def carregar_universo(
    db: AsyncSession, competencia: date
) -> IndicadoresUniverso:
    """Universo de indicadores da competencia (cacheado em processo)."""
    cached = _cache.get(competencia)
    if cached is not None:
        return cached

    async with _cache_lock:
        cached = _cache.get(competencia)
        if cached is not None:
            return cached

        comp_prev = date(
            competencia.year - 1 if competencia.month == 1 else competencia.year,
            12 if competencia.month == 1 else competencia.month - 1,
            1,
        )

        async def fetch(q, comp: date) -> list[dict]:
            rows = (await db.execute(q, {"comp": comp})).all()
            return [dict(r._mapping) for r in rows]

        dados = {
            "i": await fetch(_Q_I, competencia),
            "ii": await fetch(_Q_II, competencia),
            "ii_prev": [
                {"cnpj": r["cnpj"], "dc_bruto_prev": r["dc_bruto"]}
                for r in await fetch(_Q_II, comp_prev)
            ],
            "iii": await fetch(_Q_III, competencia),
            "iv": await fetch(_Q_IV, competencia),
            "v": await fetch(_Q_V, competencia),
            "vi": await fetch(_Q_VI, competencia),
            "vii": await fetch(_Q_VII, competencia),
            "x": await fetch(_Q_X, competencia),
            "x2": await fetch(_Q_X2, competencia),
            "x3": await fetch(_Q_X3, competencia),
            "x4": await fetch(_Q_X4, competencia),
            "x6": await fetch(_Q_X6, competencia),
        }

        rows = _montar_fundos(dados)
        medianas = _percentis_e_medianas(rows)
        universo = IndicadoresUniverso(
            competencia=competencia,
            fundos={r["cnpj"]: r for r in rows},
            medianas=medianas,
            total_fundos=len(rows),
        )
        # Cache simples com teto (12 competencias ~ 4k rows cada).
        if len(_cache) >= 12:
            _cache.pop(next(iter(_cache)))
        _cache[competencia] = universo
        return universo


async def competencias_disponiveis(
    db: AsyncSession, *, limit: int = 24
) -> list[date]:
    rows = (await db.execute(_COMPETENCIAS_QUERY, {"limit": limit})).all()
    return [r[0] for r in rows]
