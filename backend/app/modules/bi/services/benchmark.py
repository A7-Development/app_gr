"""L2 Benchmark - servico de agregacoes do mercado FIDC.

Le de `cvm_remote.*` (foreign tables apontando pra `cvm_benchmark` via
postgres_fdw). Detalhes em `docs/integracao-cvm-fidc.md`.

## Filosofia (v0.2.0 do ETL)

O ETL e **dutao burro**: `cvm.tab_i`, `cvm.tab_iv`, `cvm.tab_v`, etc. sao
espelho 1:1 do CSV da CVM (colunas com mesmo nome, lowercase, tipo inferido
por convencao de prefixo). Nao existe `percentual_pdd`, `classe_anbima`,
`patrimonio_liquido` nem qualquer outra renomeacao no DB.

**Toda derivacao vive aqui, neste service**, versionada por `ADAPTER_VERSION`
+ `decision_log` (CLAUDE.md 14). Se amanha a regra de "% inadimplencia" mudar,
muda o service + bump de versao -- nao reprocessa CSV.

## Mapeamento dos KPIs do schema -> colunas do CSV v0.2.0

| Schema (consumer)      | Origem real (CVM)                                          |
|------------------------|------------------------------------------------------------|
| cnpj_fundo             | `tab_i.cnpj_fundo_classe` (PK da linha por competencia)    |
| denominacao_social     | `tab_i.denom_social`                                       |
| classe_anbima          | `tab_i.classe` (best-effort; CVM nao usa taxonomia ANBIMA) |
| situacao               | NULL (Informe Mensal nao traz situacao do fundo)           |
| patrimonio_liquido     | `tab_iv.tab_iv_a_vl_pl`                                    |
| numero_cotistas        | NULL (dado vive no Informe Diario / Cadastral, nao ingeridos) |
| valor_total_dc         | soma(tab_v_a + tab_v_b + tab_v_c) -- prazo + inad + antecipado |
| percentual_pdd         | **derivado:** tab_v_b / (tab_v_a + tab_v_b + tab_v_c)      |
|                        | (semanticamente **% inadimplencia**, nao PDD regulatorio.  |
|                        | Rename planejado em schema v0.3.)                          |
| indice_inadimplencia   | **derivado:** (b4+b5+..+b10) / total -- inadimplentes >120d|

Padrao diferente de operacoes.py:
- **Sem escopo de tenant** (dado publico).
- Queries **SQL cruas via text()** -- deixa explicito que e federated data,
  evita declarar models SQLAlchemy pra foreign tables.
- Proveniencia marca `source_type='public:cvm_fidc'` (CLAUDE.md 13.1 / 14.6).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bi.schemas.benchmark import (
    BenchmarkEvolucao,
    BenchmarkResumo,
    FundoRow,
    FundosLista,
    PDDDistribuicao,
)
from app.modules.bi.schemas.benchmark_comparativo import (
    ComparativoResponse,
    ComposicaoFatia,
    ComposicaoFundo,
    FundoHeader,
    PontoSerie,
    PontoSerieValor,
    RankingLinha,
    RankingValor,
)
from app.modules.bi.schemas.common import KPI, CategoryValue, Point, Provenance

# Versao do adapter que ingeriu esses dados. Cresce com o schema do ETL.
# Deixar alinhado com cvm_fidc_etl/cvm_fidc/transformer.py::ADAPTER_VERSION.
ADAPTER_VERSION = "cvm_fidc_etl_v0.2.0"

# Limite de linhas retornadas pela aba Fundos (sem paginacao no MVP).
FUNDOS_LIMIT = 100

# Limite do top-N de "% inadimplencia" (schema ainda chama pdd).
TOP_PDD_LIMIT = 20

# =========================================================================
# SQL fragments reutilizaveis
#
# `_DC_TOTAL_EXPR` = denominador comum das derivacoes % inad / % pdd:
#   soma de direitos creditorios (a vencer + inadimplentes + antecipados).
# COALESCE em 0 pra evitar propagacao de NULL quando uma das 3 fatias for
# desconhecida. NULLIF no denominador pra dar NULL (nao divisao por zero)
# quando o fundo nao tem DC nenhum.
# =========================================================================

_DC_TOTAL_EXPR = """(
    COALESCE(v.tab_v_a_vl_dircred_prazo,      0) +
    COALESCE(v.tab_v_b_vl_dircred_inad,       0) +
    COALESCE(v.tab_v_c_vl_dircred_antecipado, 0)
)"""

# Inadimplente > 120 dias: soma das bandas b4..b10
_INAD_LONGO_PRAZO_EXPR = """(
    COALESCE(v.tab_v_b4_vl_inad_120,          0) +
    COALESCE(v.tab_v_b5_vl_inad_150,          0) +
    COALESCE(v.tab_v_b6_vl_inad_180,          0) +
    COALESCE(v.tab_v_b7_vl_inad_360,          0) +
    COALESCE(v.tab_v_b8_vl_inad_720,          0) +
    COALESCE(v.tab_v_b9_vl_inad_1080,         0) +
    COALESCE(v.tab_v_b10_vl_inad_maior_1080,  0)
)"""


async def _latest_competencia(db: AsyncSession) -> date | None:
    """Retorna a ultima competencia disponivel nas foreign tables.

    None se o banco esta vazio ou a ponte FDW ainda nao importou dados.
    """
    row = (
        await db.execute(
            text("SELECT MAX(competencia) AS c FROM cvm_remote.tab_i")
        )
    ).one_or_none()
    if row is None or row.c is None:
        return None
    return row.c


async def _build_provenance(
    db: AsyncSession, competencia: date | None
) -> Provenance:
    """Monta bloco de proveniencia para a resposta.

    row_count: contagem distinta de CNPJs (fundo/classe) na competencia.
    """
    if competencia is None:
        row = (
            await db.execute(
                text(
                    """
                    SELECT
                        COUNT(DISTINCT cnpj_fundo_classe) AS rc,
                        MAX(ingested_at)                  AS last_ing,
                        MAX(competencia)                  AS last_comp
                    FROM cvm_remote.tab_i
                    """
                )
            )
        ).one()
    else:
        row = (
            await db.execute(
                text(
                    """
                    SELECT
                        COUNT(DISTINCT cnpj_fundo_classe) AS rc,
                        MAX(ingested_at)                  AS last_ing,
                        MAX(competencia)                  AS last_comp
                    FROM cvm_remote.tab_i
                    WHERE competencia = :comp
                    """
                ),
                {"comp": competencia},
            )
        ).one()

    last_ing = row.last_ing
    last_comp: date | None = row.last_comp

    # last_source_updated_at: usamos competencia como proxy (CVM publica
    # dados retrospectivos; a granularidade util e mensal).
    last_source_updated: datetime | None = (
        datetime.combine(last_comp, datetime.min.time()) if last_comp else None
    )

    return Provenance(
        source_type="public:cvm_fidc",
        source_ids=[
            "cvm_remote.tab_i",
            "cvm_remote.tab_iv",
            "cvm_remote.tab_v",
        ],
        last_ingested_at=last_ing,
        last_source_updated_at=last_source_updated,
        trust_level="high",  # fonte oficial reguladora
        ingested_by_version=ADAPTER_VERSION,
        row_count=int(row.rc or 0),
    )


def _as_float(v: Any) -> float:
    if v is None:
        return 0.0
    return float(v)


def _kpi(label: str, valor: Any, unidade: str, detalhe: str | None = None) -> KPI:
    return KPI(label=label, valor=_as_float(valor), unidade=unidade, detalhe=detalhe)


# ---------------------------------------------------------------------------
# Aggregation functions (uma por L3 tab + resumo)
# ---------------------------------------------------------------------------


async def get_resumo(
    db: AsyncSession, competencia: date | None
) -> tuple[BenchmarkResumo, Provenance]:
    """KPIs agregados do mercado na competencia (ou ultima disponivel).

    - `total_fundos` = distinct CNPJ_FUNDO_CLASSE em tab_i
    - `pl_total` = SUM(tab_iv.tab_iv_a_vl_pl)
    - `pdd_mediana` = mediana(% inadimplencia) -- ver docstring do modulo
    - `inadimplencia_mediana` = mediana(% inadimplencia > 120d)
    - `cobertura_mediana` = mediana((a - b_lp) / a) -- saude da carteira
    """
    comp = competencia or await _latest_competencia(db)

    if comp is None:
        vazio = BenchmarkResumo(
            competencia=None,
            total_fundos=_kpi("Fundos reportando", 0, "un"),
            pl_total=_kpi("PL total do mercado", 0, "BRL"),
            pdd_mediana=_kpi("% inadimplencia mediana", 0, "%"),
            inadimplencia_mediana=_kpi("% inad. >120d mediana", 0, "%"),
            cobertura_mediana=_kpi("% carteira saudavel mediana", 0, "%"),
        )
        return vazio, await _build_provenance(db, None)

    # Tab I: total fundos reportando
    row_i = (
        await db.execute(
            text(
                """
                SELECT COUNT(DISTINCT cnpj_fundo_classe) AS total_fundos
                FROM cvm_remote.tab_i
                WHERE competencia = :comp
                """
            ),
            {"comp": comp},
        )
    ).one()

    # Tab IV: soma do PL do mercado
    row_iv = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(tab_iv_a_vl_pl), 0) AS pl_total
                FROM cvm_remote.tab_iv
                WHERE competencia = :comp
                """
            ),
            {"comp": comp},
        )
    ).one()

    # Tab V: medianas derivadas.
    # PERCENTILE_CONT ignora NULL naturalmente com FILTER.
    row_v = (
        await db.execute(
            text(
                f"""
                SELECT
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pct_inad)
                        FILTER (WHERE pct_inad IS NOT NULL)      AS pdd_med,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pct_inad_longo)
                        FILTER (WHERE pct_inad_longo IS NOT NULL) AS inad_med,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pct_saudavel)
                        FILTER (WHERE pct_saudavel IS NOT NULL)  AS cob_med
                FROM (
                    SELECT
                        CASE
                            WHEN {_DC_TOTAL_EXPR} > 0
                            THEN COALESCE(v.tab_v_b_vl_dircred_inad, 0)
                                 / {_DC_TOTAL_EXPR}
                        END AS pct_inad,
                        CASE
                            WHEN {_DC_TOTAL_EXPR} > 0
                            THEN {_INAD_LONGO_PRAZO_EXPR} / {_DC_TOTAL_EXPR}
                        END AS pct_inad_longo,
                        CASE
                            WHEN {_DC_TOTAL_EXPR} > 0
                            THEN COALESCE(v.tab_v_a_vl_dircred_prazo, 0)
                                 / {_DC_TOTAL_EXPR}
                        END AS pct_saudavel
                    FROM cvm_remote.tab_v v
                    WHERE v.competencia = :comp
                ) t
                """
            ),
            {"comp": comp},
        )
    ).one()

    resumo = BenchmarkResumo(
        competencia=comp.strftime("%Y-%m"),
        total_fundos=_kpi("Fundos reportando", row_i.total_fundos, "un"),
        pl_total=_kpi("PL total do mercado", row_iv.pl_total, "BRL"),
        # Fracoes 0.0-1.0 -> 0-100 pro frontend.
        pdd_mediana=_kpi("% inadimplencia mediana", _as_float(row_v.pdd_med) * 100, "%"),
        inadimplencia_mediana=_kpi(
            "% inad. >120d mediana", _as_float(row_v.inad_med) * 100, "%"
        ),
        cobertura_mediana=_kpi(
            "% carteira saudavel mediana", _as_float(row_v.cob_med) * 100, "%"
        ),
    )
    return resumo, await _build_provenance(db, comp)


async def get_pdd(
    db: AsyncSession, competencia: date | None
) -> tuple[PDDDistribuicao, Provenance]:
    """L3 "PDD" -- na verdade % inadimplencia derivado de tab_v.

    Histograma em buckets fixos + top-20 fundos por %.
    """
    comp = competencia or await _latest_competencia(db)
    if comp is None:
        return PDDDistribuicao(histograma=[], top_fundos=[]), await _build_provenance(
            db, None
        )

    # Histograma: reutiliza a derivacao no FROM derived.
    # Buckets: <1% | 1-2% | 2-5% | 5-10% | 10-20% | 20%+ | (sem DC)
    hist_rows = (
        await db.execute(
            text(
                f"""
                SELECT bucket, COUNT(*) AS qtd
                FROM (
                    SELECT CASE
                        WHEN {_DC_TOTAL_EXPR} = 0 OR {_DC_TOTAL_EXPR} IS NULL
                            THEN '(sem DC)'
                        WHEN COALESCE(v.tab_v_b_vl_dircred_inad, 0)
                             / {_DC_TOTAL_EXPR} < 0.01 THEN '< 1%'
                        WHEN COALESCE(v.tab_v_b_vl_dircred_inad, 0)
                             / {_DC_TOTAL_EXPR} < 0.02 THEN '1-2%'
                        WHEN COALESCE(v.tab_v_b_vl_dircred_inad, 0)
                             / {_DC_TOTAL_EXPR} < 0.05 THEN '2-5%'
                        WHEN COALESCE(v.tab_v_b_vl_dircred_inad, 0)
                             / {_DC_TOTAL_EXPR} < 0.10 THEN '5-10%'
                        WHEN COALESCE(v.tab_v_b_vl_dircred_inad, 0)
                             / {_DC_TOTAL_EXPR} < 0.20 THEN '10-20%'
                        ELSE '20%+'
                    END AS bucket
                    FROM cvm_remote.tab_v v
                    WHERE v.competencia = :comp
                ) t
                GROUP BY bucket
                ORDER BY CASE bucket
                    WHEN '< 1%'   THEN 1
                    WHEN '1-2%'   THEN 2
                    WHEN '2-5%'   THEN 3
                    WHEN '5-10%'  THEN 4
                    WHEN '10-20%' THEN 5
                    WHEN '20%+'   THEN 6
                    ELSE 7
                END
                """
            ),
            {"comp": comp},
        )
    ).all()

    histograma = [
        CategoryValue(
            categoria=str(r.bucket),
            valor=float(r.qtd),
            quantidade=int(r.qtd),
        )
        for r in hist_rows
    ]

    # Top N por % inadimplencia (so com total_dc > 0 e pct >= 1%).
    top_rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    COALESCE(v.denom_social, v.cnpj_fundo_classe) AS nome,
                    COALESCE(v.tab_v_b_vl_dircred_inad, 0) / {_DC_TOTAL_EXPR} AS pct
                FROM cvm_remote.tab_v v
                WHERE v.competencia = :comp
                    AND {_DC_TOTAL_EXPR} > 0
                    AND COALESCE(v.tab_v_b_vl_dircred_inad, 0) / {_DC_TOTAL_EXPR} >= 0.01
                ORDER BY pct DESC
                LIMIT :lim
                """
            ),
            {"comp": comp, "lim": TOP_PDD_LIMIT},
        )
    ).all()

    top_fundos = [
        CategoryValue(
            categoria=str(r.nome)[:60],
            valor=_as_float(r.pct) * 100,  # fracao -> %
        )
        for r in top_rows
    ]

    return PDDDistribuicao(histograma=histograma, top_fundos=top_fundos), await _build_provenance(db, comp)


async def get_evolucao(
    db: AsyncSession, meses: int = 24
) -> tuple[BenchmarkEvolucao, Provenance]:
    """L3 Evolucao -- series temporais do mercado nos ultimos N meses.

    - num_fundos = DISTINCT CNPJ_FUNDO_CLASSE em tab_i por competencia
    - pl_total = SUM(tab_iv_a_vl_pl)
    - pl_mediano = PERCENTILE_CONT(0.5) do PL
    """
    # `periodo` retorna como DATE (primeiro dia da competencia) porque o
    # schema `Point.periodo` e typed `date`. O Pydantic serializa pra
    # 'YYYY-MM-DD' no JSON, e o frontend formata pra 'YYYY-MM' na UI.
    rows = (
        await db.execute(
            text(
                """
                WITH ultimas AS (
                    SELECT DISTINCT competencia
                    FROM cvm_remote.tab_i
                    ORDER BY competencia DESC
                    LIMIT :meses
                ),
                pl AS (
                    SELECT competencia, cnpj_fundo_classe, tab_iv_a_vl_pl
                    FROM cvm_remote.tab_iv
                    WHERE competencia IN (SELECT competencia FROM ultimas)
                )
                SELECT
                    i.competencia                                         AS periodo,
                    COUNT(DISTINCT i.cnpj_fundo_classe)                   AS num_fundos,
                    COALESCE(SUM(p.tab_iv_a_vl_pl), 0)                    AS pl_total,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.tab_iv_a_vl_pl)
                        FILTER (WHERE p.tab_iv_a_vl_pl IS NOT NULL)       AS pl_mediano
                FROM cvm_remote.tab_i i
                JOIN ultimas u ON i.competencia = u.competencia
                LEFT JOIN pl p
                    ON p.competencia       = i.competencia
                   AND p.cnpj_fundo_classe = i.cnpj_fundo_classe
                GROUP BY i.competencia
                ORDER BY i.competencia
                """
            ),
            {"meses": meses},
        )
    ).all()

    pl_mediano = [Point(periodo=r.periodo, valor=_as_float(r.pl_mediano)) for r in rows]
    pl_total = [Point(periodo=r.periodo, valor=_as_float(r.pl_total)) for r in rows]
    num_fundos = [Point(periodo=r.periodo, valor=_as_float(r.num_fundos)) for r in rows]

    data = BenchmarkEvolucao(
        pl_mediano=pl_mediano,
        pl_total=pl_total,
        num_fundos=num_fundos,
    )
    return data, await _build_provenance(db, None)


async def get_fundos(
    db: AsyncSession, competencia: date | None, busca: str | None = None
) -> tuple[FundosLista, Provenance]:
    """L3 Fundos -- tabela dos top N por PL na competencia.

    JOIN tab_i + tab_iv + tab_v por (competencia, cnpj_fundo_classe).
    Calcula as derivacoes % inad inline.

    `busca`: quando preenchido, filtra por ILIKE em `denom_social` OU
    `cnpj_fundo_classe` (permite buscar por nome ou CNPJ). Em ambos os
    casos aplicamos o mesmo LIMIT para manter o payload previsivel.
    `total` continua refletindo o universo da competencia (sem o filtro)
    para dar ao usuario a sensacao de "X de Y fundos no mercado".
    """
    comp = competencia or await _latest_competencia(db)
    if comp is None:
        return FundosLista(competencia="", fundos=[], total=0), await _build_provenance(
            db, None
        )

    total_row = (
        await db.execute(
            text(
                """
                SELECT COUNT(DISTINCT cnpj_fundo_classe) AS total
                FROM cvm_remote.tab_i
                WHERE competencia = :comp
                """
            ),
            {"comp": comp},
        )
    ).one()

    # Trim + so trata como filtro se nao for string vazia.
    busca_trim = busca.strip() if busca else ""
    busca_filter = ""
    params: dict[str, Any] = {"comp": comp, "lim": FUNDOS_LIMIT}
    if busca_trim:
        busca_filter = (
            " AND (i.denom_social ILIKE :pat OR i.cnpj_fundo_classe ILIKE :pat)"
        )
        params["pat"] = f"%{busca_trim}%"

    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    i.cnpj_fundo_classe,
                    i.denom_social,
                    i.classe,
                    iv.tab_iv_a_vl_pl                                    AS pl,
                    {_DC_TOTAL_EXPR}                                     AS total_dc,
                    CASE WHEN {_DC_TOTAL_EXPR} > 0
                        THEN COALESCE(v.tab_v_b_vl_dircred_inad, 0)
                             / {_DC_TOTAL_EXPR}
                    END                                                  AS pct_inad,
                    CASE WHEN {_DC_TOTAL_EXPR} > 0
                        THEN {_INAD_LONGO_PRAZO_EXPR} / {_DC_TOTAL_EXPR}
                    END                                                  AS pct_inad_longo
                FROM cvm_remote.tab_i i
                LEFT JOIN cvm_remote.tab_iv iv
                    ON iv.competencia       = i.competencia
                   AND iv.cnpj_fundo_classe = i.cnpj_fundo_classe
                LEFT JOIN cvm_remote.tab_v v
                    ON v.competencia        = i.competencia
                   AND v.cnpj_fundo_classe  = i.cnpj_fundo_classe
                WHERE i.competencia = :comp{busca_filter}
                ORDER BY iv.tab_iv_a_vl_pl DESC NULLS LAST
                LIMIT :lim
                """
            ),
            params,
        )
    ).all()

    fundos = [
        FundoRow(
            cnpj_fundo=r.cnpj_fundo_classe,
            denominacao_social=r.denom_social,
            classe_anbima=r.classe,  # best-effort (ver docstring do modulo)
            situacao=None,  # Informe Mensal nao traz
            patrimonio_liquido=_as_float(r.pl),
            numero_cotistas=None,  # vive no Informe Diario (fora de escopo)
            valor_total_dc=_as_float(r.total_dc) if r.total_dc else None,
            percentual_pdd=(
                _as_float(r.pct_inad) * 100 if r.pct_inad is not None else None
            ),
            indice_inadimplencia=(
                _as_float(r.pct_inad_longo) * 100
                if r.pct_inad_longo is not None
                else None
            ),
        )
        for r in rows
    ]

    data = FundosLista(
        competencia=comp.strftime("%Y-%m"),
        fundos=fundos,
        total=int(total_row.total or 0),
    )
    return data, await _build_provenance(db, comp)


# ===========================================================================
# L3 Comparativo -- confronto de ate 5 fundos
#
# Entrada: cnpjs digits-only (14 digitos, normalizados pelo frontend).
# Armazenamento CVM: formatado "XX.XXX.XXX/XXXX-XX". Normalizamos no Python
# antes do SQL (mais barato que REGEXP_REPLACE em toda linha).
# ===========================================================================

# Paleta A7 Credit — slate, sky, teal, emerald, amber (CLAUDE.md 4).
_MAX_FUNDOS_COMPARATIVO = 5
_MIN_FUNDOS_COMPARATIVO = 2


def _format_cnpj_db(digits: str) -> str:
    """Converte '24290695000151' -> '24.290.695/0001-51' (formato do CVM)."""
    d = digits.strip()
    if len(d) != 14 or not d.isdigit():
        # Deixa o SQL nao encontrar (a validacao de formato e responsabilidade
        # da rota, mas evitamos injetar valores malformados no IN).
        return ""
    return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"


def _digits(cnpj: str | None) -> str:
    if not cnpj:
        return ""
    return "".join(c for c in cnpj if c.isdigit())


# Mediana = PERCENTILE_CONT(0.5) do universo da competencia.
# Direction: "desc" -> maior e melhor; "asc" -> menor e melhor.
_INDICADORES_RANKING: list[tuple[str, str, str, str]] = [
    # (key, label, unidade, direction)
    ("pl",              "PL",                   "BRL", "desc"),
    ("pl_medio",        "PL medio 3m",          "BRL", "desc"),
    ("dc_total",        "DC total",             "BRL", "desc"),
    ("pct_dc_pl",       "% DC / PL",            "%",   "desc"),
    ("pct_inad_total",  "% Inad. total",        "%",   "asc"),
    ("pct_inad_longo",  "% Inad. >120d",        "%",   "asc"),
    ("pct_saudavel",    "% Carteira saudavel",  "%",   "desc"),
    ("qt_cedentes",     "Qtd. cedentes",        "un",  "desc"),
    ("top1_cedente",    "Top-1 cedente",        "%",   "asc"),
    ("top3_cedente",    "Top-3 cedentes",       "%",   "asc"),
]

# Indicadores com serie temporal (precisam existir em N competencias recentes).
_INDICADORES_SERIES: list[str] = ["pl", "pct_inad_total"]


async def get_comparativo(
    db: AsyncSession,
    cnpjs: list[str],
    competencia: date | None,
    meses: int = 24,
) -> tuple[ComparativoResponse, Provenance]:
    """L3 Comparativo -- confronta ate 5 fundos em indicadores-chave + series.

    - `cnpjs` digits-only (14), 2..5 itens (validado na rota).
    - `competencia` opcional (fallback = ultima).
    - `meses` das series evolutivas (3..120).

    Retorna sempre um envelope completo — quando algum fundo nao tem dado
    naquela competencia, os valores vem como NULL (frontend renderiza "—").
    """
    # Normaliza cnpjs pro formato do DB. Preserva ordem recebida (define a
    # cor_index do chip no frontend).
    cnpjs_fmt = [_format_cnpj_db(c) for c in cnpjs]
    cnpjs_fmt = [c for c in cnpjs_fmt if c]

    comp = competencia or await _latest_competencia(db)

    if comp is None or not cnpjs_fmt:
        vazio = ComparativoResponse(
            competencia=comp.strftime("%Y-%m") if comp else "",
            fundos=[],
            ranking=[],
            series={},
            composicoes=[],
        )
        return vazio, await _build_provenance(db, comp)

    # -----------------------------------------------------------------
    # 1) Linha de ranking por fundo + mediana do mercado, na competencia.
    # -----------------------------------------------------------------
    indicadores_rows = (
        await db.execute(
            text(
                f"""
                WITH cedentes AS (
                    -- Concentracao dos top cedentes da parcela "DC com risco"
                    -- (tab_i2a12_pr_cedente_1..9). Valores ja sao fracoes 0..1.
                    SELECT
                        i.cnpj_fundo_classe,
                        GREATEST(
                            COALESCE(i.tab_i2a12_pr_cedente_1, 0),
                            COALESCE(i.tab_i2a12_pr_cedente_2, 0),
                            COALESCE(i.tab_i2a12_pr_cedente_3, 0),
                            COALESCE(i.tab_i2a12_pr_cedente_4, 0),
                            COALESCE(i.tab_i2a12_pr_cedente_5, 0),
                            COALESCE(i.tab_i2a12_pr_cedente_6, 0),
                            COALESCE(i.tab_i2a12_pr_cedente_7, 0),
                            COALESCE(i.tab_i2a12_pr_cedente_8, 0),
                            COALESCE(i.tab_i2a12_pr_cedente_9, 0)
                        ) AS top1,
                        (
                            COALESCE(i.tab_i2a12_pr_cedente_1, 0) +
                            COALESCE(i.tab_i2a12_pr_cedente_2, 0) +
                            COALESCE(i.tab_i2a12_pr_cedente_3, 0)
                        ) AS top3
                    FROM cvm_remote.tab_i i
                    WHERE i.competencia = :comp
                ),
                linha AS (
                    SELECT
                        i.cnpj_fundo_classe,
                        i.denom_social,
                        i.classe,
                        iv.tab_iv_a_vl_pl            AS pl,
                        iv.tab_iv_b_vl_pl_medio      AS pl_medio,
                        {_DC_TOTAL_EXPR}             AS dc_total,
                        CASE WHEN iv.tab_iv_a_vl_pl > 0
                             THEN {_DC_TOTAL_EXPR} / iv.tab_iv_a_vl_pl
                        END                          AS pct_dc_pl,
                        CASE WHEN {_DC_TOTAL_EXPR} > 0
                             THEN COALESCE(v.tab_v_b_vl_dircred_inad, 0)
                                  / {_DC_TOTAL_EXPR}
                        END                          AS pct_inad_total,
                        CASE WHEN {_DC_TOTAL_EXPR} > 0
                             THEN {_INAD_LONGO_PRAZO_EXPR} / {_DC_TOTAL_EXPR}
                        END                          AS pct_inad_longo,
                        CASE WHEN {_DC_TOTAL_EXPR} > 0
                             THEN COALESCE(v.tab_v_a_vl_dircred_prazo, 0)
                                  / {_DC_TOTAL_EXPR}
                        END                          AS pct_saudavel,
                        vii.tab_vii_b1_1_qt_cedente  AS qt_cedentes,
                        c.top1                       AS top1_cedente,
                        c.top3                       AS top3_cedente
                    FROM cvm_remote.tab_i i
                    LEFT JOIN cvm_remote.tab_iv iv
                        ON iv.competencia       = i.competencia
                       AND iv.cnpj_fundo_classe = i.cnpj_fundo_classe
                    LEFT JOIN cvm_remote.tab_v v
                        ON v.competencia        = i.competencia
                       AND v.cnpj_fundo_classe  = i.cnpj_fundo_classe
                    LEFT JOIN cvm_remote.tab_vii vii
                        ON vii.competencia      = i.competencia
                       AND vii.cnpj_fundo_classe= i.cnpj_fundo_classe
                    LEFT JOIN cedentes c
                        ON c.cnpj_fundo_classe  = i.cnpj_fundo_classe
                    WHERE i.competencia = :comp
                )
                SELECT
                    -- Valores por fundo selecionado
                    jsonb_object_agg(
                        l.cnpj_fundo_classe,
                        jsonb_build_object(
                            'denom_social',    l.denom_social,
                            'classe',          l.classe,
                            'pl',              l.pl,
                            'pl_medio',        l.pl_medio,
                            'dc_total',        l.dc_total,
                            'pct_dc_pl',       l.pct_dc_pl,
                            'pct_inad_total',  l.pct_inad_total,
                            'pct_inad_longo',  l.pct_inad_longo,
                            'pct_saudavel',    l.pct_saudavel,
                            'qt_cedentes',     l.qt_cedentes,
                            'top1_cedente',    l.top1_cedente,
                            'top3_cedente',    l.top3_cedente
                        )
                    ) FILTER (WHERE l.cnpj_fundo_classe = ANY(:cnpjs))  AS por_fundo,
                    -- Medianas de mercado (todo o universo da competencia)
                    jsonb_build_object(
                        'pl',             PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.pl)             FILTER (WHERE l.pl IS NOT NULL),
                        'pl_medio',       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.pl_medio)       FILTER (WHERE l.pl_medio IS NOT NULL),
                        'dc_total',       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.dc_total)       FILTER (WHERE l.dc_total IS NOT NULL AND l.dc_total > 0),
                        'pct_dc_pl',      PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.pct_dc_pl)      FILTER (WHERE l.pct_dc_pl IS NOT NULL),
                        'pct_inad_total', PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.pct_inad_total) FILTER (WHERE l.pct_inad_total IS NOT NULL),
                        'pct_inad_longo', PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.pct_inad_longo) FILTER (WHERE l.pct_inad_longo IS NOT NULL),
                        'pct_saudavel',   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.pct_saudavel)   FILTER (WHERE l.pct_saudavel IS NOT NULL),
                        'qt_cedentes',    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.qt_cedentes)    FILTER (WHERE l.qt_cedentes IS NOT NULL),
                        'top1_cedente',   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.top1_cedente)   FILTER (WHERE l.top1_cedente IS NOT NULL AND l.top1_cedente > 0),
                        'top3_cedente',   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.top3_cedente)   FILTER (WHERE l.top3_cedente IS NOT NULL AND l.top3_cedente > 0)
                    ) AS medianas
                FROM linha l
                """
            ),
            {"comp": comp, "cnpjs": cnpjs_fmt},
        )
    ).one()

    por_fundo: dict[str, dict[str, Any]] = indicadores_rows.por_fundo or {}
    medianas: dict[str, Any] = indicadores_rows.medianas or {}

    # Header dos fundos na ordem da request (define cor_index).
    headers: list[FundoHeader] = []
    for idx, cnpj_fmt in enumerate(cnpjs_fmt):
        if idx >= _MAX_FUNDOS_COMPARATIVO:
            break
        row_f = por_fundo.get(cnpj_fmt) or {}
        headers.append(
            FundoHeader(
                cnpj=_digits(cnpj_fmt),
                denom_social=row_f.get("denom_social"),
                classe_anbima=row_f.get("classe"),
                cor_index=idx,
            )
        )

    # Ranking: uma linha por indicador.
    ranking: list[RankingLinha] = []
    for key, label, unidade, direction in _INDICADORES_RANKING:
        mediana_raw = medianas.get(key)
        mediana = _as_float_nullable(mediana_raw)
        if unidade == "%" and mediana is not None:
            mediana = mediana * 100

        valores: list[RankingValor] = []
        for h in headers:
            row_f = por_fundo.get(_format_cnpj_db(h.cnpj)) or {}
            raw = row_f.get(key)
            v = _as_float_nullable(raw)
            if unidade == "%" and v is not None:
                v = v * 100
            valores.append(RankingValor(cnpj=h.cnpj, valor=v))

        ranking.append(
            RankingLinha(
                key=key,
                label=label,
                unidade=unidade,
                direction=direction,
                mediana_mercado=mediana,
                valores=valores,
            )
        )

    # -----------------------------------------------------------------
    # 2) Series temporais — N meses mais recentes.
    # -----------------------------------------------------------------
    series_rows = (
        await db.execute(
            text(
                f"""
                WITH ultimas AS (
                    SELECT DISTINCT competencia
                    FROM cvm_remote.tab_i
                    ORDER BY competencia DESC
                    LIMIT :meses
                ),
                base AS (
                    SELECT
                        i.competencia,
                        i.cnpj_fundo_classe,
                        iv.tab_iv_a_vl_pl AS pl,
                        CASE WHEN {_DC_TOTAL_EXPR} > 0
                             THEN COALESCE(v.tab_v_b_vl_dircred_inad, 0)
                                  / {_DC_TOTAL_EXPR}
                        END AS pct_inad_total
                    FROM cvm_remote.tab_i i
                    JOIN ultimas u ON i.competencia = u.competencia
                    LEFT JOIN cvm_remote.tab_iv iv
                        ON iv.competencia       = i.competencia
                       AND iv.cnpj_fundo_classe = i.cnpj_fundo_classe
                    LEFT JOIN cvm_remote.tab_v v
                        ON v.competencia        = i.competencia
                       AND v.cnpj_fundo_classe  = i.cnpj_fundo_classe
                )
                SELECT
                    competencia,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pl)
                        FILTER (WHERE pl IS NOT NULL)             AS pl_mediana,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pct_inad_total)
                        FILTER (WHERE pct_inad_total IS NOT NULL) AS pct_inad_mediana,
                    jsonb_object_agg(
                        cnpj_fundo_classe,
                        jsonb_build_object(
                            'pl',             pl,
                            'pct_inad_total', pct_inad_total
                        )
                    ) FILTER (WHERE cnpj_fundo_classe = ANY(:cnpjs)) AS por_fundo
                FROM base
                GROUP BY competencia
                ORDER BY competencia
                """
            ),
            {"meses": meses, "cnpjs": cnpjs_fmt},
        )
    ).all()

    series: dict[str, list[PontoSerie]] = {key: [] for key in _INDICADORES_SERIES}
    for r in series_rows:
        comp_str: str = r.competencia.strftime("%Y-%m")
        por_f = r.por_fundo or {}

        for key in _INDICADORES_SERIES:
            mediana_col = "pl_mediana" if key == "pl" else "pct_inad_mediana"
            mediana_raw = getattr(r, mediana_col)
            mediana = _as_float_nullable(mediana_raw)
            if key.startswith("pct_") and mediana is not None:
                mediana = mediana * 100

            vals: list[PontoSerieValor] = []
            for h in headers:
                row_f = por_f.get(_format_cnpj_db(h.cnpj)) or {}
                raw = row_f.get(key)
                v = _as_float_nullable(raw)
                if key.startswith("pct_") and v is not None:
                    v = v * 100
                vals.append(PontoSerieValor(cnpj=h.cnpj, valor=v))

            series[key].append(
                PontoSerie(competencia=comp_str, mediana=mediana, valores=vals)
            )

    # -----------------------------------------------------------------
    # 3) Composicao snapshot por fundo — ativo, setores, SCR devedor.
    # -----------------------------------------------------------------
    comp_rows = (
        await db.execute(
            text(
                """
                SELECT
                    i.cnpj_fundo_classe,
                    i.tab_i_vl_ativo             AS ativo_total,
                    i.tab_i2a_vl_dircred_risco   AS dc_com_risco,
                    i.tab_i2b_vl_dircred_sem_risco AS dc_sem_risco,
                    i.tab_i2c_vl_vlmob           AS valores_mobiliarios,
                    i.tab_i2d_vl_titpub_fed      AS tpf,
                    i.tab_i2e_vl_cdb             AS cdb,
                    i.tab_i2g_vl_outro_rf        AS outros_rf,
                    i.tab_i2h_vl_cota_fidc       AS cota_fidc,
                    ii.tab_ii_a_vl_indust        AS seg_industrial,
                    ii.tab_ii_c_vl_comerc        AS seg_comercial,
                    ii.tab_ii_d_vl_serv          AS seg_servicos,
                    ii.tab_ii_e_vl_agroneg      AS seg_agro,
                    ii.tab_ii_f_vl_financ        AS seg_financeiro,
                    ii.tab_ii_g_vl_credito       AS seg_credito,
                    ii.tab_ii_h_vl_factor        AS seg_factoring,
                    ii.tab_ii_i_vl_setor_publico AS seg_setor_publico,
                    ii.tab_ii_j_vl_judicial      AS seg_judicial,
                    ii.tab_ii_b_vl_imobil        AS seg_imobiliario,
                    x.tab_x_scr_risco_devedor_aa AS scr_aa,
                    x.tab_x_scr_risco_devedor_a  AS scr_a,
                    x.tab_x_scr_risco_devedor_b  AS scr_b,
                    x.tab_x_scr_risco_devedor_c  AS scr_c,
                    x.tab_x_scr_risco_devedor_d  AS scr_d,
                    x.tab_x_scr_risco_devedor_e  AS scr_e,
                    x.tab_x_scr_risco_devedor_f  AS scr_f,
                    x.tab_x_scr_risco_devedor_g  AS scr_g,
                    x.tab_x_scr_risco_devedor_h  AS scr_h
                FROM cvm_remote.tab_i i
                LEFT JOIN cvm_remote.tab_ii ii
                    ON ii.competencia       = i.competencia
                   AND ii.cnpj_fundo_classe = i.cnpj_fundo_classe
                LEFT JOIN cvm_remote.tab_x x
                    ON x.competencia        = i.competencia
                   AND x.cnpj_fundo_classe  = i.cnpj_fundo_classe
                WHERE i.competencia    = :comp
                  AND i.cnpj_fundo_classe = ANY(:cnpjs)
                """
            ),
            {"comp": comp, "cnpjs": cnpjs_fmt},
        )
    ).all()

    comp_por_cnpj: dict[str, Any] = {r.cnpj_fundo_classe: r for r in comp_rows}

    composicoes: list[ComposicaoFundo] = []
    for h in headers:
        r = comp_por_cnpj.get(_format_cnpj_db(h.cnpj))
        if r is None:
            composicoes.append(
                ComposicaoFundo(
                    cnpj=h.cnpj,
                    ativo_total=None,
                    ativo=[],
                    setores_top=[],
                    scr_devedor=[],
                )
            )
            continue

        ativo_total = _as_float_nullable(r.ativo_total)

        ativo = _build_fatias(
            [
                ("DC com risco",  _as_float_nullable(r.dc_com_risco)),
                ("DC sem risco",  _as_float_nullable(r.dc_sem_risco)),
                ("Valores mob.",  _as_float_nullable(r.valores_mobiliarios)),
                ("TPF",           _as_float_nullable(r.tpf)),
                ("CDB",           _as_float_nullable(r.cdb)),
                ("Outros RF",     _as_float_nullable(r.outros_rf)),
                ("Cotas FIDC",    _as_float_nullable(r.cota_fidc)),
            ],
            total=ativo_total,
        )

        setores_raw = [
            ("Industrial",    _as_float_nullable(r.seg_industrial)),
            ("Comercial",     _as_float_nullable(r.seg_comercial)),
            ("Servicos",      _as_float_nullable(r.seg_servicos)),
            ("Agronegocio",   _as_float_nullable(r.seg_agro)),
            ("Financeiro",    _as_float_nullable(r.seg_financeiro)),
            ("Credito",       _as_float_nullable(r.seg_credito)),
            ("Factoring",     _as_float_nullable(r.seg_factoring)),
            ("Setor publico", _as_float_nullable(r.seg_setor_publico)),
            ("Judicial",      _as_float_nullable(r.seg_judicial)),
            ("Imobiliario",   _as_float_nullable(r.seg_imobiliario)),
        ]
        setores_total = sum(v for _, v in setores_raw if v is not None and v > 0) or None
        setores_top = _build_fatias(
            sorted(setores_raw, key=lambda t: t[1] or 0, reverse=True)[:5],
            total=setores_total,
        )

        scr_raw = [
            ("AA", _parse_pct_text(r.scr_aa)),
            ("A",  _parse_pct_text(r.scr_a)),
            ("B",  _parse_pct_text(r.scr_b)),
            ("C",  _parse_pct_text(r.scr_c)),
            ("D",  _parse_pct_text(r.scr_d)),
            ("E",  _parse_pct_text(r.scr_e)),
            ("F",  _parse_pct_text(r.scr_f)),
            ("G",  _parse_pct_text(r.scr_g)),
            ("H",  _parse_pct_text(r.scr_h)),
        ]
        scr_devedor = [
            ComposicaoFatia(categoria=cat, valor=v or 0.0, percentual=v)
            for cat, v in scr_raw
            if v is not None and v > 0
        ]

        composicoes.append(
            ComposicaoFundo(
                cnpj=h.cnpj,
                ativo_total=ativo_total,
                ativo=ativo,
                setores_top=setores_top,
                scr_devedor=scr_devedor,
            )
        )

    response = ComparativoResponse(
        competencia=comp.strftime("%Y-%m"),
        fundos=headers,
        ranking=ranking,
        series=series,
        composicoes=composicoes,
    )
    return response, await _build_provenance(db, comp)


def _as_float_nullable(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_pct_text(v: Any) -> float | None:
    """Converte valores text da tab_x (SCR AA..H) em float.

    O CSV CVM entrega esses campos como texto. Formatos esperados: '0.123',
    '12.3', '12,3', '12.3%', ou vazio/None.
    """
    if v is None:
        return None
    s = str(v).strip().replace("%", "").replace(",", ".")
    if not s:
        return None
    try:
        n = float(s)
    except ValueError:
        return None
    # Se vier como fracao (0..1), converte pra %
    return n * 100 if n <= 1.0 else n


def _build_fatias(
    items: list[tuple[str, float | None]], total: float | None
) -> list[ComposicaoFatia]:
    """Normaliza (categoria, valor) em ComposicaoFatia + percentual opcional.

    Filtra fatias com valor None/0. Percentual apenas quando `total` > 0.
    """
    out: list[ComposicaoFatia] = []
    for cat, v in items:
        if v is None or v <= 0:
            continue
        pct = (v / total * 100) if (total and total > 0) else None
        out.append(ComposicaoFatia(categoria=cat, valor=v, percentual=pct))
    return out
