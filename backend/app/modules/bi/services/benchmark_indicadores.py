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

Estrategia FDW-friendly: cada CTE e um scan de UMA tabela remota filtrado por
competencia (qual simples, pushdown garantido); os joins acontecem localmente
no gr_db. O resultado do universo (~4k linhas) e cacheado em processo por
competencia (dado mensal estatico; CLAUDE.md sec 2 permite cache em-processo
no MVP).
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Pontos medios (dias) dos 10 buckets de prazo da tab_v/tab_vi.
_BUCKET_MIDPOINTS = (15, 45, 75, 105, 135, 165, 270, 540, 900, 1260)

_UNIVERSO_QUERY = text(
    """
    WITH i AS (
        SELECT
            cnpj_fundo_classe AS cnpj,
            denom_social,
            NULLIF(tab_i_vl_ativo, 0) AS ativo,
            COALESCE(tab_i2a_vl_dircred_risco, 0)
              + COALESCE(tab_i2b_vl_dircred_sem_risco, 0) AS dc_liq,
            COALESCE(tab_i2a11_vl_reducao_recup, 0)
              + COALESCE(tab_i2b11_vl_reducao_recup, 0) AS pdd,
            COALESCE(tab_i1_vl_disp, 0)
              + COALESCE(tab_i2d_vl_titpub_fed, 0)
              + COALESCE(tab_i2e_vl_cdb, 0)
              + COALESCE(tab_i2f_vl_oper_comprom, 0)
              + COALESCE(tab_i2g_vl_outro_rf, 0)
              + COALESCE(tab_i2c5_vl_cota_fif, 0)
              + COALESCE(tab_i2c5_vl_cota_fundo_icvm555, 0)
              + COALESCE(tab_i4a_vl_cprazo, 0) AS alta_liquidez
        FROM cvm_remote.tab_i
        WHERE competencia = :comp
    ),
    ii AS (
        SELECT cnpj_fundo_classe AS cnpj, NULLIF(tab_ii_vl_carteira, 0) AS dc_bruto
        FROM cvm_remote.tab_ii
        WHERE competencia = :comp
    ),
    ii_prev AS (
        SELECT cnpj_fundo_classe AS cnpj, NULLIF(tab_ii_vl_carteira, 0) AS dc_bruto_prev
        FROM cvm_remote.tab_ii
        WHERE competencia = (:comp::date - INTERVAL '1 month')::date
    ),
    iii AS (
        SELECT cnpj_fundo_classe AS cnpj, COALESCE(tab_iii_vl_passivo, 0) AS passivo
        FROM cvm_remote.tab_iii
        WHERE competencia = :comp
    ),
    iv AS (
        SELECT cnpj_fundo_classe AS cnpj,
               NULLIF(tab_iv_a_vl_pl, 0) AS pl,
               tab_iv_b_vl_pl_medio AS pl_medio
        FROM cvm_remote.tab_iv
        WHERE competencia = :comp
    ),
    v AS (
        SELECT cnpj_fundo_classe AS cnpj,
            COALESCE(tab_v_a_vl_dircred_prazo, 0) AS av_total,
            COALESCE(tab_v_b_vl_dircred_inad, 0) AS inad,
            COALESCE(tab_v_b4_vl_inad_120, 0) + COALESCE(tab_v_b5_vl_inad_150, 0)
              + COALESCE(tab_v_b6_vl_inad_180, 0) + COALESCE(tab_v_b7_vl_inad_360, 0)
              + COALESCE(tab_v_b8_vl_inad_720, 0) + COALESCE(tab_v_b9_vl_inad_1080, 0)
              + COALESCE(tab_v_b10_vl_inad_maior_1080, 0) AS inad_90,
            COALESCE(tab_v_a1_vl_prazo_venc_30, 0) * 15
              + COALESCE(tab_v_a2_vl_prazo_venc_60, 0) * 45
              + COALESCE(tab_v_a3_vl_prazo_venc_90, 0) * 75
              + COALESCE(tab_v_a4_vl_prazo_venc_120, 0) * 105
              + COALESCE(tab_v_a5_vl_prazo_venc_150, 0) * 135
              + COALESCE(tab_v_a6_vl_prazo_venc_180, 0) * 165
              + COALESCE(tab_v_a7_vl_prazo_venc_360, 0) * 270
              + COALESCE(tab_v_a8_vl_prazo_venc_720, 0) * 540
              + COALESCE(tab_v_a9_vl_prazo_venc_1080, 0) * 900
              + COALESCE(tab_v_a10_vl_prazo_venc_maior_1080, 0) * 1260 AS prazo_wsum
        FROM cvm_remote.tab_v
        WHERE competencia = :comp
    ),
    vi AS (
        SELECT cnpj_fundo_classe AS cnpj,
            COALESCE(tab_vi_a_vl_dircred_prazo, 0) AS av_total,
            COALESCE(tab_vi_b_vl_dircred_inad, 0) AS inad,
            COALESCE(tab_vi_b4_vl_inad_120, 0) + COALESCE(tab_vi_b5_vl_inad_150, 0)
              + COALESCE(tab_vi_b6_vl_inad_180, 0) + COALESCE(tab_vi_b7_vl_inad_360, 0)
              + COALESCE(tab_vi_b8_vl_inad_720, 0) + COALESCE(tab_vi_b9_vl_inad_1080, 0)
              + COALESCE(tab_vi_b10_vl_inad_maior_1080, 0) AS inad_90,
            COALESCE(tab_vi_a1_vl_prazo_venc_30, 0) * 15
              + COALESCE(tab_vi_a2_vl_prazo_venc_60, 0) * 45
              + COALESCE(tab_vi_a3_vl_prazo_venc_90, 0) * 75
              + COALESCE(tab_vi_a4_vl_prazo_venc_120, 0) * 105
              + COALESCE(tab_vi_a5_vl_prazo_venc_150, 0) * 135
              + COALESCE(tab_vi_a6_vl_prazo_venc_180, 0) * 165
              + COALESCE(tab_vi_a7_vl_prazo_venc_360, 0) * 270
              + COALESCE(tab_vi_a8_vl_prazo_venc_720, 0) * 540
              + COALESCE(tab_vi_a9_vl_prazo_venc_1080, 0) * 900
              + COALESCE(tab_vi_a10_vl_prazo_venc_maior_1080, 0) * 1260 AS prazo_wsum
        FROM cvm_remote.tab_vi
        WHERE competencia = :comp
    ),
    vii AS (
        SELECT cnpj_fundo_classe AS cnpj,
            COALESCE(tab_vii_a1_2_vl_dircred_risco, 0)
              + COALESCE(tab_vii_a2_2_vl_dircred_sem_risco, 0) AS aquisicoes,
            COALESCE(tab_vii_d_2_vl_recompra, 0) AS recompra,
            COALESCE(tab_vii_d_3_vl_contab_recompra, 0) AS recompra_contabil
        FROM cvm_remote.tab_vii
        WHERE competencia = :comp
    ),
    x AS (
        -- SCR: colunas TEXT com string numerica. Eixo OPERACAO, todas as letras
        -- (a regua AA..H soma o DC bruto — validado; ha arrasto de devedor).
        SELECT cnpj_fundo_classe AS cnpj,
            COALESCE(NULLIF(TRIM(tab_x_debito_tribut), '')::numeric, 0) AS divida_ativa,
            (
              COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_aa), '')::numeric, 0)
              + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_a), '')::numeric, 0)
              + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_b), '')::numeric, 0)
              + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_c), '')::numeric, 0)
            ) AS scr_aa_c,
            (
              COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_d), '')::numeric, 0)
              + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_e), '')::numeric, 0)
              + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_f), '')::numeric, 0)
              + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_g), '')::numeric, 0)
              + COALESCE(NULLIF(TRIM(tab_x_scr_risco_oper_h), '')::numeric, 0)
            ) AS scr_d_h
        FROM cvm_remote.tab_x
        WHERE competencia = :comp
    ),
    x2 AS (
        SELECT cnpj_fundo_classe AS cnpj,
            SUM(tab_x_qt_cota * tab_x_vl_cota) AS pl_classes,
            SUM(tab_x_qt_cota * tab_x_vl_cota)
              FILTER (WHERE tab_x_classe_serie ILIKE '%subord%') AS pl_subord
        FROM cvm_remote.tab_x_2
        WHERE competencia = :comp AND tab_x_qt_cota IS NOT NULL AND tab_x_vl_cota IS NOT NULL
        GROUP BY 1
    ),
    x23 AS (
        -- Yield efetivo (resultado das classes) + rentab da sub "pura"
        -- (subordinada que NAO e mezanino), ponderada por PL quando ha N series.
        SELECT x2s.cnpj_fundo_classe AS cnpj,
            SUM(x2s.tab_x_qt_cota * x2s.tab_x_vl_cota * x3.tab_x_vl_rentab_mes / 100)
              AS resultado_mes,
            SUM(x2s.tab_x_qt_cota * x2s.tab_x_vl_cota * x3.tab_x_vl_rentab_mes)
              FILTER (WHERE x2s.tab_x_classe_serie ILIKE '%subord%'
                        AND x2s.tab_x_classe_serie NOT ILIKE '%mezanino%')
              AS rentab_sub_wsum,
            SUM(x2s.tab_x_qt_cota * x2s.tab_x_vl_cota)
              FILTER (WHERE x2s.tab_x_classe_serie ILIKE '%subord%'
                        AND x2s.tab_x_classe_serie NOT ILIKE '%mezanino%')
              AS pl_sub_puro
        FROM cvm_remote.tab_x_2 x2s
        JOIN cvm_remote.tab_x_3 x3
          ON x3.cnpj_fundo_classe = x2s.cnpj_fundo_classe
         AND x3.competencia = x2s.competencia
         AND x3.tab_x_classe_serie = x2s.tab_x_classe_serie
        WHERE x2s.competencia = :comp
          AND x2s.tab_x_qt_cota IS NOT NULL AND x2s.tab_x_vl_cota IS NOT NULL
          AND x3.tab_x_vl_rentab_mes IS NOT NULL
        GROUP BY 1
    ),
    x4 AS (
        SELECT cnpj_fundo_classe AS cnpj,
            SUM(CASE tab_x_tp_oper
                  WHEN 'Captações no Mês' THEN COALESCE(tab_x_vl_total, 0)
                  WHEN 'Resgates no Mês' THEN -COALESCE(tab_x_vl_total, 0)
                  WHEN 'Amortizações' THEN -COALESCE(tab_x_vl_total, 0)
                  ELSE 0 END) AS captacao_liq
        FROM cvm_remote.tab_x_4
        WHERE competencia = :comp
        GROUP BY 1
    ),
    x6 AS (
        SELECT cnpj_fundo_classe AS cnpj,
            AVG(tab_x_pr_desemp_real - tab_x_pr_desemp_esperado)
              FILTER (WHERE COALESCE(tab_x_pr_desemp_esperado, 0) > 0) AS atingimento_pp
        FROM cvm_remote.tab_x_6
        WHERE competencia = :comp
        GROUP BY 1
    ),
    base AS (
        SELECT
            i.cnpj,
            i.denom_social,
            iv.pl::float AS pl,
            iv.pl_medio::float AS pl_medio,
            (100 * x2.pl_subord / NULLIF(iv.pl, 0))::float AS subordinacao_pct,
            (100 * iii.passivo / i.ativo)::float AS passivo_ativo_pct,
            (100 * i.dc_liq / i.ativo)::float AS dc_ativo_pct,
            (100 * i.alta_liquidez / NULLIF(iv.pl, 0))::float AS alta_liquidez_pl_pct,
            CASE WHEN COALESCE(v.av_total, 0) + COALESCE(vi.av_total, 0) > 0
                 THEN ((COALESCE(v.prazo_wsum, 0) + COALESCE(vi.prazo_wsum, 0))
                       / (COALESCE(v.av_total, 0) + COALESCE(vi.av_total, 0)))::float
            END AS prazo_medio_dias,
            (100 * (COALESCE(v.inad, 0) + COALESCE(vi.inad, 0)) / ii.dc_bruto)::float
              AS inad_total_pct,
            (100 * (COALESCE(v.inad_90, 0) + COALESCE(vi.inad_90, 0)) / ii.dc_bruto)::float
              AS inad_90_pct,
            CASE WHEN COALESCE(v.inad, 0) + COALESCE(vi.inad, 0) > 0
                 THEN (100 * i.pdd / (COALESCE(v.inad, 0) + COALESCE(vi.inad, 0)))::float
            END AS cobertura_pdd_pct,
            (100 * i.pdd / NULLIF(iv.pl, 0))::float AS pdd_pl_pct,
            (100 * COALESCE(vii.recompra, 0) / ii.dc_bruto)::float AS recompra_dc_pct,
            (COALESCE(vii.recompra_contabil, 0) - COALESCE(vii.recompra, 0))::float
              AS desagio_recompra,
            (100 * COALESCE(x4.captacao_liq, 0) / NULLIF(iv.pl, 0))::float
              AS captacao_liq_pl_pct,
            (100 * COALESCE(vii.aquisicoes, 0) / ii.dc_bruto)::float AS giro_pct,
            (x23.rentab_sub_wsum / NULLIF(x23.pl_sub_puro, 0))::float AS rentab_sub_pct,
            x6.atingimento_pp::float AS atingimento_pp,
            CASE WHEN COALESCE(x.scr_aa_c, 0) + COALESCE(x.scr_d_h, 0) > 0
                 THEN (100 * x.scr_d_h / (x.scr_aa_c + x.scr_d_h))::float
            END AS scr_dh_pct,
            (100 * x23.resultado_mes
              / NULLIF((ii.dc_bruto + COALESCE(ii_prev.dc_bruto_prev, ii.dc_bruto)) / 2, 0)
            )::float AS yield_efetivo_pct,
            (100 * COALESCE(x.divida_ativa, 0) / ii.dc_bruto)::float AS divida_ativa_pct
        FROM i
        LEFT JOIN ii ON ii.cnpj = i.cnpj
        LEFT JOIN ii_prev ON ii_prev.cnpj = i.cnpj
        LEFT JOIN iii ON iii.cnpj = i.cnpj
        LEFT JOIN iv ON iv.cnpj = i.cnpj
        LEFT JOIN v ON v.cnpj = i.cnpj
        LEFT JOIN vi ON vi.cnpj = i.cnpj
        LEFT JOIN vii ON vii.cnpj = i.cnpj
        LEFT JOIN x ON x.cnpj = i.cnpj
        LEFT JOIN x2 ON x2.cnpj = i.cnpj
        LEFT JOIN x23 ON x23.cnpj = i.cnpj
        LEFT JOIN x4 ON x4.cnpj = i.cnpj
        LEFT JOIN x6 ON x6.cnpj = i.cnpj
        WHERE iv.pl > 0
    )
    SELECT * FROM base
    """
)

_COMPETENCIAS_QUERY = text(
    """
    SELECT DISTINCT competencia FROM cvm_remote.tab_iv
    ORDER BY competencia DESC
    LIMIT :limit
    """
)


@dataclass
class IndicadoresUniverso:
    """Universo de uma competencia: linhas por fundo (dicts) + medianas."""

    competencia: date
    fundos: dict[str, dict]  # cnpj -> row dict (indicadores + percentis)
    medianas: dict[str, float | None]
    total_fundos: int


# Indicadores que ganham percentil. Direcao: True = maior e melhor (percentil
# alto = bom). Usada no front pro radar/realce; o percentil cru e SEMPRE
# "fracao do universo abaixo de mim" (percent_rank ascendente).
INDICADOR_DIRECAO: dict[str, bool] = {
    "pl": True,
    "subordinacao_pct": True,
    "passivo_ativo_pct": False,
    "dc_ativo_pct": True,
    "alta_liquidez_pl_pct": True,
    "prazo_medio_dias": False,
    "inad_total_pct": False,
    "inad_90_pct": False,
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

# Cache em-processo por competencia (dado mensal estatico; MVP — CLAUDE.md §2).
_cache: dict[date, IndicadoresUniverso] = {}


def _percentis_e_medianas(rows: list[dict]) -> dict[str, float | None]:
    """Anota `<indicador>_pct_rank` (0-100, fracao do universo ESTRITAMENTE
    abaixo) em cada row, in place, e retorna as medianas do universo."""
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
        # Rank por busca binaria (bisect_left) — O(n log n) total.
        for r in rows:
            v = r.get(campo)
            r[f"{campo}_rank"] = (
                round(100 * bisect.bisect_left(valores, v) / n, 1)
                if v is not None and n > 1
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

    rows = [
        dict(r._mapping)
        for r in (await db.execute(_UNIVERSO_QUERY, {"comp": competencia})).all()
    ]
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
