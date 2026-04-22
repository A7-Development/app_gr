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
    AdminLinha,
    BenchmarkAdmins,
    BenchmarkCondom,
    BenchmarkEvolucao,
    BenchmarkResumo,
    CondomPonto,
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
from app.modules.bi.schemas.fundo import (
    AtrasoBuckets,
    AtrasoPonto,
    CarteiraPonto,
    CedenteLinha,
    CotistasPonto,
    CotistasTipoPonto,
    DesempenhoGap,
    DesempenhoPonto,
    FichaFundo,
    FluxoCotasPonto,
    Garantias,
    Identificacao,
    LiquidezFaixas,
    LiquidezPonto,
    PLPonto,
    PLSubclassesPonto,
    PrazoMedioPonto,
    RecompraPonto,
    RentAcumuladaPonto,
    RentPonto,
    SCRLinha,
    SetorLinha,
    SubclasseLinha,
)

# Versao do adapter que ingeriu esses dados. Cresce com o schema do ETL.
# Deixar alinhado com cvm_fidc_etl/cvm_fidc/transformer.py::ADAPTER_VERSION.
ADAPTER_VERSION = "cvm_fidc_etl_v0.3.0"

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


# Default do range quando o usuario nao informa — ultimos 12 meses a partir da
# ultima competencia disponivel. Mantem o mesmo default do preset frontend `12m`.
_DEFAULT_RANGE_MESES = 12


def _norm_first_of_month(d: date) -> date:
    """Garante que a data cai no primeiro dia do mes (competencia = month floor)."""
    return date(d.year, d.month, 1)


def _sub_months(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) - months
    y, m = divmod(total, 12)
    return date(y, m + 1, 1)


async def _resolve_range(
    db: AsyncSession,
    periodo_inicio: date | None,
    periodo_fim: date | None,
) -> tuple[date, date] | None:
    """Resolve o range (inicio, fim) em competencias mensais.

    - `periodo_fim` ausente → ultima competencia disponivel.
    - `periodo_inicio` ausente → 12 meses antes de `periodo_fim`.
    - Inicio sempre <= fim. Ambos sao normalizados para o primeiro dia do mes.

    Retorna None quando o banco nao tem dado (sem competencia).
    """
    fim = periodo_fim or await _latest_competencia(db)
    if fim is None:
        return None
    fim = _norm_first_of_month(fim)
    inicio = (
        _norm_first_of_month(periodo_inicio)
        if periodo_inicio
        else _sub_months(fim, _DEFAULT_RANGE_MESES - 1)
    )
    if inicio > fim:
        inicio = fim
    return inicio, fim


def _build_benchmark_filter_sql(
    tipo_fundo: list[str] | None,
    incluir_exclusivos: bool,
    table_alias: str = "i",
) -> tuple[str, dict[str, Any]]:
    """Monta o fragmento `AND ...` de filtros comuns do benchmark.

    - `tipo_fundo`: valores de `tab_i.tp_fundo_classe` — ex.: ['Fundo'], ['Classe'].
    - `incluir_exclusivos=False` (default) filtra `fundo_exclusivo != 'S'`.

    Retorna (sql_fragment, params). O fragment comeca com ` AND` quando ha
    clausulas; string vazia quando nao ha filtro adicional.
    """
    fragments: list[str] = []
    params: dict[str, Any] = {}
    a = table_alias
    if tipo_fundo:
        fragments.append(f"AND {a}.tp_fundo_classe = ANY(:bm_tipo_fundo)")
        params["bm_tipo_fundo"] = list(tipo_fundo)
    if not incluir_exclusivos:
        # Exclui fundo_exclusivo = 'S'. Inclui 'N' e NULL (defensivo — CVM as
        # vezes publica nulo para fundos antigos).
        fragments.append(
            f"AND ({a}.fundo_exclusivo IS NULL OR {a}.fundo_exclusivo <> 'S')"
        )
    return (" " + " ".join(fragments) if fragments else ""), params


async def _build_provenance(
    db: AsyncSession, competencia: date | None
) -> Provenance:
    """Monta bloco de proveniencia para a resposta.

    Para a fonte CVM (publica, federada via FDW), o pipeline de ingestao
    roda no repo `etl-cvm` separado — nao tem entrada no `decision_log` do
    GR. Usamos `MAX(cvm_remote.tab_i.ingested_at)` como proxy de "ultima
    entrega do ETL externo" (preenche `last_sync_at`).

    row_count: contagem distinta de CNPJs (fundo/classe) na competencia.
    """
    if competencia is None:
        row = (
            await db.execute(
                text(
                    """
                    SELECT
                        COUNT(DISTINCT cnpj_fundo_classe) AS rc,
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
                        MAX(competencia)                  AS last_comp
                    FROM cvm_remote.tab_i
                    WHERE competencia = :comp
                    """
                ),
                {"comp": competencia},
            )
        ).one()

    last_comp: date | None = row.last_comp

    # last_source_updated_at: usamos competencia como proxy (CVM publica
    # dados retrospectivos; a granularidade util e mensal).
    last_source_updated: datetime | None = (
        datetime.combine(last_comp, datetime.min.time()) if last_comp else None
    )

    # last_sync_at: proxy por MAX(ingested_at) da tabela principal da CVM.
    # Global (sem filtro de competencia) — representa "ultima entrega do ETL
    # externo", independente da janela analitica em tela.
    last_sync = (
        await db.execute(text("SELECT MAX(ingested_at) FROM cvm_remote.tab_i"))
    ).scalar_one_or_none()

    return Provenance(
        source_type="public:cvm_fidc",
        source_ids=[
            "cvm_remote.tab_i",
            "cvm_remote.tab_iv",
            "cvm_remote.tab_v",
        ],
        last_sync_at=last_sync,
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
    db: AsyncSession,
    periodo_inicio: date | None = None,
    periodo_fim: date | None = None,
    tipo_fundo: list[str] | None = None,
    incluir_exclusivos: bool = False,
) -> tuple[BenchmarkEvolucao, Provenance]:
    """L3 Evolucao -- series temporais do mercado dentro do range mensal.

    - num_fundos = DISTINCT CNPJ_FUNDO_CLASSE em tab_i por competencia
    - pl_total = SUM(tab_iv_a_vl_pl)
    - pl_mediano = PERCENTILE_CONT(0.5) do PL

    Filtros aplicados em `tab_i` (tipo_fundo + fundo_exclusivo). `pl` vem de
    `tab_iv` via LEFT JOIN e herda o filtro naturalmente pela chave composta.
    """
    rng = await _resolve_range(db, periodo_inicio, periodo_fim)
    if rng is None:
        return (
            BenchmarkEvolucao(pl_mediano=[], pl_total=[], num_fundos=[]),
            await _build_provenance(db, None),
        )
    inicio, fim = rng

    filter_sql, filter_params = _build_benchmark_filter_sql(
        tipo_fundo, incluir_exclusivos, table_alias="i"
    )

    # `periodo` retorna como DATE (primeiro dia da competencia) porque o
    # schema `Point.periodo` e typed `date`. O Pydantic serializa pra
    # 'YYYY-MM-DD' no JSON, e o frontend formata pra 'YYYY-MM' na UI.
    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    i.competencia                                         AS periodo,
                    COUNT(DISTINCT i.cnpj_fundo_classe)                   AS num_fundos,
                    COALESCE(SUM(iv.tab_iv_a_vl_pl), 0)                   AS pl_total,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY iv.tab_iv_a_vl_pl)
                        FILTER (WHERE iv.tab_iv_a_vl_pl IS NOT NULL)      AS pl_mediano
                FROM cvm_remote.tab_i i
                LEFT JOIN cvm_remote.tab_iv iv
                    ON iv.competencia       = i.competencia
                   AND iv.cnpj_fundo_classe = i.cnpj_fundo_classe
                WHERE i.competencia BETWEEN :inicio AND :fim{filter_sql}
                GROUP BY i.competencia
                ORDER BY i.competencia
                """
            ),
            {"inicio": inicio, "fim": fim, **filter_params},
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


# ---------------------------------------------------------------------------
# Mercado — Top administradoras
# ---------------------------------------------------------------------------

_TOP_ADMINS_LIMIT = 10


async def get_admins(
    db: AsyncSession,
    periodo_fim: date | None,
    tipo_fundo: list[str] | None = None,
    incluir_exclusivos: bool = False,
) -> tuple[BenchmarkAdmins, Provenance]:
    """Top 10 administradoras na competencia-fim do range.

    Ranking snapshot: para garantir consistencia visual, o ranking e sempre
    calculado na `periodo_fim` (ou ultima disponivel). Mudar o range so
    desloca a competencia de referencia — mantem a pergunta 'quem e top hoje'.

    Retorna 2 rankings: por quantidade de fundos e por PL sob administracao.
    Ambos incluem as duas metricas nas linhas (para tooltip rico).
    """
    comp = (
        _norm_first_of_month(periodo_fim)
        if periodo_fim
        else await _latest_competencia(db)
    )
    if comp is None:
        return (
            BenchmarkAdmins(
                competencia="",
                top_por_quantidade=[],
                top_por_pl=[],
                total_admins=0,
            ),
            await _build_provenance(db, None),
        )

    filter_sql, filter_params = _build_benchmark_filter_sql(
        tipo_fundo, incluir_exclusivos, table_alias="i"
    )

    # Agrega por cnpj_admin para evitar colisao entre admins homonimos.
    # `admin` pode variar em caixa/pontuacao entre meses — usamos MAX na
    # competencia para display (so 1 linha por admin naquela competencia).
    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    i.cnpj_admin,
                    MAX(i.admin)                                 AS admin,
                    COUNT(DISTINCT i.cnpj_fundo_classe)          AS qtd,
                    COALESCE(SUM(iv.tab_iv_a_vl_pl), 0)          AS pl
                FROM cvm_remote.tab_i i
                LEFT JOIN cvm_remote.tab_iv iv
                    ON iv.competencia       = i.competencia
                   AND iv.cnpj_fundo_classe = i.cnpj_fundo_classe
                WHERE i.competencia = :comp
                    AND i.admin IS NOT NULL{filter_sql}
                GROUP BY i.cnpj_admin
                """
            ),
            {"comp": comp, **filter_params},
        )
    ).all()

    linhas = [
        AdminLinha(
            cnpj_admin=r.cnpj_admin,
            admin=str(r.admin),
            quantidade_fundos=int(r.qtd or 0),
            pl_total=_as_float(r.pl),
        )
        for r in rows
    ]

    top_qtd = sorted(linhas, key=lambda x: x.quantidade_fundos, reverse=True)[
        :_TOP_ADMINS_LIMIT
    ]
    top_pl = sorted(linhas, key=lambda x: x.pl_total, reverse=True)[:_TOP_ADMINS_LIMIT]

    data = BenchmarkAdmins(
        competencia=comp.strftime("%Y-%m"),
        top_por_quantidade=top_qtd,
        top_por_pl=top_pl,
        total_admins=len(linhas),
    )
    return data, await _build_provenance(db, comp)


# ---------------------------------------------------------------------------
# Mercado — Condominio (Aberto vs Fechado)
# ---------------------------------------------------------------------------


async def get_condom(
    db: AsyncSession,
    periodo_inicio: date | None = None,
    periodo_fim: date | None = None,
    tipo_fundo: list[str] | None = None,
    incluir_exclusivos: bool = False,
) -> tuple[BenchmarkCondom, Provenance]:
    """Distribuicao Aberto vs Fechado — snapshot na fim + serie mensal.

    Filtra `condom IN ('ABERTO','FECHADO')` — fundos em liquidacao publicados
    como 'NA'/'0' sao ignorados (nao contam como aberto nem fechado).
    """
    rng = await _resolve_range(db, periodo_inicio, periodo_fim)
    if rng is None:
        return (
            BenchmarkCondom(
                competencia="",
                aberto_qtd=0,
                fechado_qtd=0,
                aberto_pct=0.0,
                fechado_pct=0.0,
                evolucao=[],
            ),
            await _build_provenance(db, None),
        )
    inicio, fim = rng

    filter_sql, filter_params = _build_benchmark_filter_sql(
        tipo_fundo, incluir_exclusivos, table_alias="i"
    )

    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    i.competencia                                              AS periodo,
                    COUNT(DISTINCT i.cnpj_fundo_classe) FILTER (
                        WHERE UPPER(i.condom) = 'ABERTO'
                    )                                                          AS aberto_qtd,
                    COUNT(DISTINCT i.cnpj_fundo_classe) FILTER (
                        WHERE UPPER(i.condom) = 'FECHADO'
                    )                                                          AS fechado_qtd
                FROM cvm_remote.tab_i i
                WHERE i.competencia BETWEEN :inicio AND :fim{filter_sql}
                GROUP BY i.competencia
                ORDER BY i.competencia
                """
            ),
            {"inicio": inicio, "fim": fim, **filter_params},
        )
    ).all()

    evolucao: list[CondomPonto] = []
    for r in rows:
        a = int(r.aberto_qtd or 0)
        f = int(r.fechado_qtd or 0)
        total = a + f
        a_pct = (a / total * 100) if total > 0 else 0.0
        f_pct = (f / total * 100) if total > 0 else 0.0
        evolucao.append(
            CondomPonto(
                periodo=r.periodo,
                aberto_qtd=a,
                fechado_qtd=f,
                aberto_pct=a_pct,
                fechado_pct=f_pct,
            )
        )

    # Snapshot na competencia-fim. Se nao tiver linha para a fim exata (rng
    # de 1 mes vazio), cai na ultima da serie.
    snapshot = next(
        (p for p in reversed(evolucao) if p.periodo == fim),
        evolucao[-1] if evolucao else None,
    )
    if snapshot is None:
        return (
            BenchmarkCondom(
                competencia=fim.strftime("%Y-%m"),
                aberto_qtd=0,
                fechado_qtd=0,
                aberto_pct=0.0,
                fechado_pct=0.0,
                evolucao=[],
            ),
            await _build_provenance(db, fim),
        )

    data = BenchmarkCondom(
        competencia=snapshot.periodo.strftime("%Y-%m"),
        aberto_qtd=snapshot.aberto_qtd,
        fechado_qtd=snapshot.fechado_qtd,
        aberto_pct=snapshot.aberto_pct,
        fechado_pct=snapshot.fechado_pct,
        evolucao=evolucao,
    )
    return data, await _build_provenance(db, snapshot.periodo)


async def get_fundos(
    db: AsyncSession, competencia: date | None, busca: str | None = None
) -> tuple[FundosLista, Provenance]:
    """L3 Fundos -- tabela dos top N por PL na competencia.

    JOIN tab_i + tab_iv + tab_v por (competencia, cnpj_fundo_classe).
    Calcula as derivacoes % inad inline.

    `busca`: quando preenchido, e quebrado em tokens por whitespace e
    cada token precisa dar match via ILIKE em `denom_social` OU
    `cnpj_fundo_classe` (AND entre tokens, OR entre colunas). Isso
    permite busca por fragmento ("exo"), por palavras fora de ordem
    ("fidc exodus" acha "EXODUS FUNDO...FIDC") e tambem por CNPJ
    parcial. O LIMIT e o mesmo; `total` continua refletindo o universo
    da competencia (sem o filtro) para dar ao usuario a sensacao de
    "X de Y fundos no mercado".
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

    # Trim + quebra em tokens; cada token vira um predicado ILIKE que
    # casa com denom_social OU cnpj_fundo_classe. Tokens sao combinados
    # via AND para que "fidc exodus" ache "EXODUS FIDC MULTISSETORIAL"
    # mesmo fora de ordem.
    busca_trim = busca.strip() if busca else ""
    busca_filter = ""
    params: dict[str, Any] = {"comp": comp, "lim": FUNDOS_LIMIT}
    if busca_trim:
        tokens = [t for t in busca_trim.split() if t]
        if tokens:
            clauses: list[str] = []
            for idx, tok in enumerate(tokens):
                key = f"pat{idx}"
                clauses.append(
                    f"(i.denom_social ILIKE :{key}"
                    f" OR i.cnpj_fundo_classe ILIKE :{key})"
                )
                params[key] = f"%{tok}%"
            busca_filter = " AND " + " AND ".join(clauses)

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


# ===========================================================================
# L3 Ficha do Fundo -- snapshot + series ~24m de 1 fundo
#
# Chaves de todas as queries: cnpj_fundo_classe (masked) + competencia.
# CVM armazena CNPJ como "XX.XXX.XXX/XXXX-XX"; a rota passa digits-only.
# ===========================================================================

# Pontos medios (dias) dos buckets "a vencer" da tab_v -- ordem alinhada
# com a1..a10: 0-30, 30-60, 60-90, 90-120, 120-150, 150-180, 180-360,
# 360-720, 720-1080, >1080. Usados pra calcular duration aproximada.
_PRAZO_MIDPOINTS = [15.0, 45.0, 75.0, 105.0, 135.0, 165.0, 270.0, 540.0, 900.0, 1260.0]

# PT-BR: o que a CVM NAO publica e o frontend precisa sinalizar como "nao
# reproduzivel". Texto estavel -- alterar aqui se a lista evoluir.
_LIMITACOES_FICHA: list[str] = [
    "Rating, perspectiva e analistas -- dado proprietario da agencia",
    "Natureza dos DC (duplicata/cheque/confissao) -- CVM agrega apenas por setor economico",
    "Recompras e WOP -- dado operacional interno, nao reportado a CVM",
    "Concentracao de sacados -- CVM coleta apenas top-9 cedentes",
    "Top-10/20 cedentes -- CVM so publica top-9",
    "Rentabilidade x CDI -- CDI externo nao ingerido no MVP",
]

# Humanizacao dos rotulos setoriais (tab_ii_*). Chave = nome da coluna.
_SETOR_LABELS: dict[str, str] = {
    "tab_ii_a_vl_indust":        "Industrial",
    "tab_ii_b_vl_imobil":        "Imobiliario",
    "tab_ii_c_vl_comerc":        "Comercial",
    "tab_ii_d_vl_serv":          "Servicos",
    "tab_ii_e_vl_agroneg":       "Agronegocio",
    "tab_ii_f_vl_financ":        "Financeiro",
    "tab_ii_g_vl_credito":       "Credito",
    "tab_ii_h_vl_factor":        "Factoring",
    "tab_ii_i_vl_setor_publico": "Setor publico",
    "tab_ii_j_vl_judicial":      "Judicial",
    "tab_ii_k_vl_marca":         "Marca/IP",
}


def _parse_num_text(v: Any) -> float:
    """Converte texto/numerico em float (tolerante a ',' decimal e '%').

    Fallback 0.0 pra evitar propagar None em agregacoes -- o consumer decide
    se quer tratar ausencia como zero (setores, fluxo_cotas) ou como
    omissao (secoes inteiras retornam lista vazia antes de chamar aqui).
    """
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "").replace(",", ".")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _yyyymm(d: date) -> str:
    return d.strftime("%Y-%m")


async def get_cvm_range(db: AsyncSession) -> tuple[date | None, date | None]:
    """Min/max competencia globais no CVM (para o preset 'ALL' da UI)."""
    row = (
        await db.execute(
            text("SELECT MIN(competencia) AS min_c, MAX(competencia) AS max_c FROM cvm_remote.competencias")
        )
    ).one()
    return row.min_c, row.max_c


async def get_fundo(
    db: AsyncSession,
    cnpj: str,
    periodo_inicio: date | None = None,
    periodo_fim: date | None = None,
) -> tuple[FichaFundo, Provenance]:
    """Ficha completa do fundo: snapshot + series dentro do periodo.

    `cnpj` digits-only (14). Converte para o formato mascarado da CVM
    antes do SQL.

    `periodo_inicio` / `periodo_fim` recortam as series. Se algum for None,
    cai para o min/max disponivel do fundo em `cvm_remote.tab_i` -- o BETWEEN
    naturalmente lida com datas fora do intervalo da CVM.

    Raises ValueError quando o fundo nao existe na base (rota converte em 404).
    """
    cnpj_fmt = _format_cnpj_db(cnpj)
    if not cnpj_fmt:
        raise ValueError(f"CNPJ malformado: {cnpj!r}")

    # -----------------------------------------------------------------
    # 1) Competencias de referencia (atual = max, primeira = min).
    # -----------------------------------------------------------------
    comps = (
        await db.execute(
            text(
                """
                SELECT MAX(competencia) AS max_c, MIN(competencia) AS min_c
                FROM cvm_remote.tab_i
                WHERE cnpj_fundo_classe = :cnpj
                """
            ),
            {"cnpj": cnpj_fmt},
        )
    ).one()
    comp_atual: date | None = comps.max_c
    comp_primeira: date | None = comps.min_c
    if comp_atual is None or comp_primeira is None:
        raise ValueError(f"Fundo {cnpj} sem dados no CVM")

    inicio = periodo_inicio if periodo_inicio is not None else comp_primeira
    fim = periodo_fim if periodo_fim is not None else comp_atual
    params_range = {"cnpj": cnpj_fmt, "inicio": inicio, "fim": fim}

    # -----------------------------------------------------------------
    # 2) Identificacao (1 linha, competencia atual).
    # -----------------------------------------------------------------
    ident_row = (
        await db.execute(
            text(
                """
                SELECT
                    denom_social,
                    tp_fundo_classe,
                    condom,
                    classe,
                    admin,
                    cnpj_admin,
                    prazo_conversao_cota,
                    prazo_pagto_resgate
                FROM cvm_remote.tab_i
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia       = :comp
                """
            ),
            {"cnpj": cnpj_fmt, "comp": comp_atual},
        )
    ).one()

    identificacao = Identificacao(
        cnpj=cnpj_fmt,
        denom_social=ident_row.denom_social,
        tp_fundo_classe=ident_row.tp_fundo_classe,
        condom=ident_row.condom,
        classe=ident_row.classe,
        admin=ident_row.admin,
        cnpj_admin=ident_row.cnpj_admin,
        prazo_conversao_cota=ident_row.prazo_conversao_cota,
        prazo_pagto_resgate=ident_row.prazo_pagto_resgate,
        competencia_atual=_yyyymm(comp_atual),
        competencia_primeira=_yyyymm(comp_primeira),
    )

    # -----------------------------------------------------------------
    # 3) pl_serie -- tab_iv_a_vl_pl (PL) + tab_iv_b_vl_pl_medio (PL medio 3m)
    # -----------------------------------------------------------------
    pl_rows = (
        await db.execute(
            text(
                """
                SELECT competencia,
                       tab_iv_a_vl_pl       AS pl,
                       tab_iv_b_vl_pl_medio AS pl_medio
                FROM cvm_remote.tab_iv
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia BETWEEN :inicio AND :fim
                ORDER BY competencia
                """
            ),
            params_range,
        )
    ).all()
    pl_serie = [
        PLPonto(
            competencia=r.competencia,
            pl=_as_float(r.pl),
            pl_medio=_as_float(r.pl_medio) if r.pl_medio is not None else None,
        )
        for r in pl_rows
    ]
    # Indice rapido pra cruzar na atraso_serie (pct_pl_total).
    pl_por_comp: dict[date, float] = {p.competencia: p.pl for p in pl_serie}

    # -----------------------------------------------------------------
    # 4) carteira_serie -- Ativo (Tabela I) do Informe Mensal FIDC
    #
    # Fonte unica: `cvm_remote.tab_i`. Traz todas as 13 categorias + subtotal
    # Carteira (I.2) + total Ativo (I). Ocultacao de linhas 100% zeradas fica
    # a cargo do frontend (regra de apresentacao, nao de dado).
    # -----------------------------------------------------------------
    cart_rows = (
        await db.execute(
            text(
                """
                SELECT
                    competencia,
                    COALESCE(tab_i1_vl_disp,             0) AS disp,
                    COALESCE(tab_i2a_vl_dircred_risco,   0) AS dc_risco,
                    COALESCE(tab_i2b_vl_dircred_sem_risco,0) AS dc_sem_risco,
                    COALESCE(tab_i2c_vl_vlmob,           0) AS vlmob,
                    COALESCE(tab_i2d_vl_titpub_fed,      0) AS tit_pub,
                    COALESCE(tab_i2e_vl_cdb,             0) AS cdb,
                    COALESCE(tab_i2f_vl_oper_comprom,    0) AS oper_comprom,
                    COALESCE(tab_i2g_vl_outro_rf,        0) AS outros_rf,
                    COALESCE(tab_i2h_vl_cota_fidc,       0) AS cotas_fidc,
                    COALESCE(tab_i2i_vl_cota_fidc_np,    0) AS cotas_fidc_np,
                    COALESCE(tab_i2j_vl_contrato_futuro, 0) AS contrato_futuro,
                    COALESCE(tab_i2_vl_carteira,         0) AS carteira_sub,
                    COALESCE(tab_i3_vl_posicao_deriv,    0) AS deriv,
                    COALESCE(tab_i4_vl_outro_ativo,      0) AS outro_ativo,
                    COALESCE(tab_i2a11_vl_reducao_recup, 0) AS pdd_aprox,
                    COALESCE(tab_i_vl_ativo,             0) AS ativo_total
                FROM cvm_remote.tab_i
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia BETWEEN :inicio AND :fim
                ORDER BY competencia
                """
            ),
            params_range,
        )
    ).all()
    carteira_serie = [
        CarteiraPonto(
            competencia=r.competencia,
            disp=_as_float(r.disp),
            dc_risco=_as_float(r.dc_risco),
            dc_sem_risco=_as_float(r.dc_sem_risco),
            vlmob=_as_float(r.vlmob),
            tit_pub=_as_float(r.tit_pub),
            cdb=_as_float(r.cdb),
            oper_comprom=_as_float(r.oper_comprom),
            outros_rf=_as_float(r.outros_rf),
            cotas_fidc=_as_float(r.cotas_fidc),
            cotas_fidc_np=_as_float(r.cotas_fidc_np),
            contrato_futuro=_as_float(r.contrato_futuro),
            carteira_sub=_as_float(r.carteira_sub),
            deriv=_as_float(r.deriv),
            outro_ativo=_as_float(r.outro_ativo),
            pdd_aprox=_as_float(r.pdd_aprox),
            ativo_total=_as_float(r.ativo_total),
        )
        for r in cart_rows
    ]

    # -----------------------------------------------------------------
    # 5) atraso_serie -- buckets b1..b10 + pct sobre PL
    # -----------------------------------------------------------------
    atraso_rows = (
        await db.execute(
            text(
                """
                SELECT
                    competencia,
                    COALESCE(tab_v_b1_vl_inad_30,         0) AS b0_30,
                    COALESCE(tab_v_b2_vl_inad_60,         0) AS b30_60,
                    COALESCE(tab_v_b3_vl_inad_90,         0) AS b60_90,
                    COALESCE(tab_v_b4_vl_inad_120,        0) AS b90_120,
                    COALESCE(tab_v_b5_vl_inad_150,        0) AS b120_150,
                    COALESCE(tab_v_b6_vl_inad_180,        0) AS b150_180,
                    COALESCE(tab_v_b7_vl_inad_360,        0) AS b180_360,
                    COALESCE(tab_v_b8_vl_inad_720,        0) AS b360_720,
                    COALESCE(tab_v_b9_vl_inad_1080,       0) AS b720_1080,
                    COALESCE(tab_v_b10_vl_inad_maior_1080,0) AS b1080_plus
                FROM cvm_remote.tab_v
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia BETWEEN :inicio AND :fim
                ORDER BY competencia
                """
            ),
            params_range,
        )
    ).all()

    atraso_serie: list[AtrasoPonto] = []
    for r in atraso_rows:
        buckets = AtrasoBuckets(
            b0_30=_as_float(r.b0_30),
            b30_60=_as_float(r.b30_60),
            b60_90=_as_float(r.b60_90),
            b90_120=_as_float(r.b90_120),
            b120_150=_as_float(r.b120_150),
            b150_180=_as_float(r.b150_180),
            b180_360=_as_float(r.b180_360),
            b360_720=_as_float(r.b360_720),
            b720_1080=_as_float(r.b720_1080),
            b1080_plus=_as_float(r.b1080_plus),
        )
        total = (
            buckets.b0_30 + buckets.b30_60 + buckets.b60_90 + buckets.b90_120
            + buckets.b120_150 + buckets.b150_180 + buckets.b180_360
            + buckets.b360_720 + buckets.b720_1080 + buckets.b1080_plus
        )
        pl = pl_por_comp.get(r.competencia, 0.0)
        pct = (total / pl * 100) if pl > 0 else 0.0
        atraso_serie.append(
            AtrasoPonto(
                competencia=r.competencia,
                buckets=buckets,
                pct_pl_total=pct,
            )
        )

    # -----------------------------------------------------------------
    # 6) prazo_medio_serie -- weighted avg via midpoints
    # -----------------------------------------------------------------
    prazo_rows = (
        await db.execute(
            text(
                """
                SELECT
                    competencia,
                    COALESCE(tab_v_a1_vl_prazo_venc_30,          0) AS a1,
                    COALESCE(tab_v_a2_vl_prazo_venc_60,          0) AS a2,
                    COALESCE(tab_v_a3_vl_prazo_venc_90,          0) AS a3,
                    COALESCE(tab_v_a4_vl_prazo_venc_120,         0) AS a4,
                    COALESCE(tab_v_a5_vl_prazo_venc_150,         0) AS a5,
                    COALESCE(tab_v_a6_vl_prazo_venc_180,         0) AS a6,
                    COALESCE(tab_v_a7_vl_prazo_venc_360,         0) AS a7,
                    COALESCE(tab_v_a8_vl_prazo_venc_720,         0) AS a8,
                    COALESCE(tab_v_a9_vl_prazo_venc_1080,        0) AS a9,
                    COALESCE(tab_v_a10_vl_prazo_venc_maior_1080, 0) AS a10
                FROM cvm_remote.tab_v
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia BETWEEN :inicio AND :fim
                ORDER BY competencia
                """
            ),
            params_range,
        )
    ).all()

    prazo_medio_serie: list[PrazoMedioPonto] = []
    for r in prazo_rows:
        vals = [
            _as_float(r.a1), _as_float(r.a2), _as_float(r.a3), _as_float(r.a4),
            _as_float(r.a5), _as_float(r.a6), _as_float(r.a7), _as_float(r.a8),
            _as_float(r.a9), _as_float(r.a10),
        ]
        soma = sum(vals)
        if soma > 0:
            dias = sum(v * mp for v, mp in zip(vals, _PRAZO_MIDPOINTS, strict=True)) / soma
        else:
            dias = 0.0
        prazo_medio_serie.append(
            PrazoMedioPonto(competencia=r.competencia, dias_aprox=dias)
        )

    # -----------------------------------------------------------------
    # 7) cedentes -- top-9 da competencia atual (tab_i2a12_*)
    # -----------------------------------------------------------------
    ced_row = (
        await db.execute(
            text(
                """
                SELECT
                    tab_i2a12_cpf_cnpj_cedente_1 AS cnpj_1, tab_i2a12_pr_cedente_1 AS pr_1,
                    tab_i2a12_cpf_cnpj_cedente_2 AS cnpj_2, tab_i2a12_pr_cedente_2 AS pr_2,
                    tab_i2a12_cpf_cnpj_cedente_3 AS cnpj_3, tab_i2a12_pr_cedente_3 AS pr_3,
                    tab_i2a12_cpf_cnpj_cedente_4 AS cnpj_4, tab_i2a12_pr_cedente_4 AS pr_4,
                    tab_i2a12_cpf_cnpj_cedente_5 AS cnpj_5, tab_i2a12_pr_cedente_5 AS pr_5,
                    tab_i2a12_cpf_cnpj_cedente_6 AS cnpj_6, tab_i2a12_pr_cedente_6 AS pr_6,
                    tab_i2a12_cpf_cnpj_cedente_7 AS cnpj_7, tab_i2a12_pr_cedente_7 AS pr_7,
                    tab_i2a12_cpf_cnpj_cedente_8 AS cnpj_8, tab_i2a12_pr_cedente_8 AS pr_8,
                    tab_i2a12_cpf_cnpj_cedente_9 AS cnpj_9, tab_i2a12_pr_cedente_9 AS pr_9
                FROM cvm_remote.tab_i
                WHERE cnpj_fundo_classe = :cnpj AND competencia = :comp
                """
            ),
            {"cnpj": cnpj_fmt, "comp": comp_atual},
        )
    ).one_or_none()

    cedentes: list[CedenteLinha] = []
    if ced_row is not None:
        for rank in range(1, 10):
            pr = getattr(ced_row, f"pr_{rank}", None)
            cnpj_c = getattr(ced_row, f"cnpj_{rank}", None)
            pct_val = _as_float(pr)
            # CVM as vezes grava fracao 0..1, as vezes percentual 0..100.
            # Normaliza pra percentual pra UI.
            pct_norm = pct_val * 100 if 0 < pct_val <= 1 else pct_val
            if pct_norm <= 0 and not cnpj_c:
                continue
            cedentes.append(
                CedenteLinha(
                    cpf_cnpj=cnpj_c if cnpj_c else None,
                    rank=rank,
                    pct=pct_norm,
                )
            )

    # -----------------------------------------------------------------
    # 8) setores -- tab_ii, melt das colunas de valor setorial
    # -----------------------------------------------------------------
    setores_cols = list(_SETOR_LABELS.keys())
    setores_select = ",\n                    ".join(
        f"COALESCE({c}, 0) AS {c}" for c in setores_cols
    )
    setores_row = (
        await db.execute(
            text(
                f"""
                SELECT
                    {setores_select}
                FROM cvm_remote.tab_ii
                WHERE cnpj_fundo_classe = :cnpj AND competencia = :comp
                """
            ),
            {"cnpj": cnpj_fmt, "comp": comp_atual},
        )
    ).one_or_none()

    setores: list[SetorLinha] = []
    if setores_row is not None:
        pares = [
            (_SETOR_LABELS[c], _as_float(getattr(setores_row, c, 0)))
            for c in setores_cols
        ]
        total_set = sum(v for _, v in pares if v > 0)
        for nome, val in pares:
            if val <= 0:
                continue
            pct = (val / total_set * 100) if total_set > 0 else 0.0
            setores.append(SetorLinha(setor=nome, valor=val, pct=pct))
        setores.sort(key=lambda s: s.valor, reverse=True)

    # -----------------------------------------------------------------
    # 9) subclasses -- join tab_x_1 + tab_x_2 (classe_serie; sem id_subclasse em x_2)
    # -----------------------------------------------------------------
    # tab_x_2.qt_cota e text(NULL no Puma); tab_x_2.vl_cota text; tab_x_1.nr_cotst int.
    sub_rows = (
        await db.execute(
            text(
                """
                SELECT
                    x1.tab_x_classe_serie AS classe_serie,
                    x1.id_subclasse        AS id_subclasse,
                    x1.tab_x_nr_cotst      AS nr_cotst,
                    x2.tab_x_qt_cota       AS qt_cota,
                    x2.tab_x_vl_cota       AS vl_cota
                FROM cvm_remote.tab_x_1 x1
                LEFT JOIN cvm_remote.tab_x_2 x2
                    ON x2.competencia        = x1.competencia
                   AND x2.cnpj_fundo_classe  = x1.cnpj_fundo_classe
                   AND x2.tab_x_classe_serie = x1.tab_x_classe_serie
                WHERE x1.cnpj_fundo_classe = :cnpj
                  AND x1.competencia       = :comp
                """
            ),
            {"cnpj": cnpj_fmt, "comp": comp_atual},
        )
    ).all()

    subclasses_raw: list[tuple[str, str | None, int, float, float, float]] = []
    for r in sub_rows:
        qt = _parse_num_text(r.qt_cota)
        vl = _parse_num_text(r.vl_cota)
        pl_sub = qt * vl
        subclasses_raw.append(
            (str(r.classe_serie), r.id_subclasse, int(r.nr_cotst or 0), qt, vl, pl_sub)
        )
    pl_sub_total = sum(row[5] for row in subclasses_raw) or 0.0
    subclasses = [
        SubclasseLinha(
            classe_serie=classe,
            id_subclasse=id_sub,
            qt_cota=qt,
            vl_cota=vl,
            pl=pl_sub,
            pct_pl=(pl_sub / pl_sub_total * 100) if pl_sub_total > 0 else 0.0,
            nr_cotst=nr,
        )
        for classe, id_sub, nr, qt, vl, pl_sub in subclasses_raw
    ]

    # -----------------------------------------------------------------
    # 10) cotistas_serie -- pivota tab_x_1 no Python
    # -----------------------------------------------------------------
    cotst_rows = (
        await db.execute(
            text(
                """
                SELECT competencia, tab_x_classe_serie AS classe_serie, tab_x_nr_cotst AS nr
                FROM cvm_remote.tab_x_1
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia BETWEEN :inicio AND :fim
                ORDER BY competencia
                """
            ),
            params_range,
        )
    ).all()
    cotistas_map: dict[date, dict[str, int]] = {}
    for r in cotst_rows:
        cotistas_map.setdefault(r.competencia, {})[str(r.classe_serie)] = int(r.nr or 0)
    cotistas_serie = [
        CotistasPonto(competencia=comp, por_serie=mapa)
        for comp, mapa in sorted(cotistas_map.items())
    ]

    # -----------------------------------------------------------------
    # 10b) cotistas_tipo_serie -- tab_x_1_1 (cotistas por TIPO de investidor)
    # 16 tipos × {Senior, Subordinada}. NAO quebra por serie.
    # -----------------------------------------------------------------
    _COTST_TIPOS = (
        "pf", "pj_nao_financ", "pj_financ", "banco", "invnr", "rpps",
        "eapc", "efpc", "fii", "cota_fidc", "outro_fi", "clube",
        "segur", "corretora_distrib", "capitaliz", "outro",
    )
    cotst_tipo_cols = ", ".join(
        f"tab_x_nr_cotst_senior_{t} AS s_{t}, tab_x_nr_cotst_subord_{t} AS b_{t}"
        for t in _COTST_TIPOS
    )
    cotst_tipo_rows = (
        await db.execute(
            text(
                f"""
                SELECT competencia, {cotst_tipo_cols}
                FROM cvm_remote.tab_x_1_1
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia BETWEEN :inicio AND :fim
                ORDER BY competencia
                """
            ),
            params_range,
        )
    ).all()
    cotistas_tipo_serie = [
        CotistasTipoPonto(
            competencia=r.competencia,
            senior={t: int(getattr(r, f"s_{t}") or 0) for t in _COTST_TIPOS},
            subord={t: int(getattr(r, f"b_{t}") or 0) for t in _COTST_TIPOS},
        )
        for r in cotst_tipo_rows
    ]

    # -----------------------------------------------------------------
    # 11) pl_subclasses_serie -- pivota tab_x_2 no Python (qt * vl)
    # -----------------------------------------------------------------
    plsub_rows = (
        await db.execute(
            text(
                """
                SELECT
                    competencia,
                    tab_x_classe_serie AS classe_serie,
                    tab_x_qt_cota      AS qt,
                    tab_x_vl_cota      AS vl
                FROM cvm_remote.tab_x_2
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia BETWEEN :inicio AND :fim
                ORDER BY competencia
                """
            ),
            params_range,
        )
    ).all()
    plsub_map: dict[date, dict[str, float]] = {}
    for r in plsub_rows:
        qt = _parse_num_text(r.qt)
        vl = _parse_num_text(r.vl)
        plsub_map.setdefault(r.competencia, {})[str(r.classe_serie)] = qt * vl
    pl_subclasses_serie = [
        PLSubclassesPonto(competencia=comp, por_subclasse=mapa)
        for comp, mapa in sorted(plsub_map.items())
    ]

    # -----------------------------------------------------------------
    # 12) rent_serie -- pivota tab_x_3
    # -----------------------------------------------------------------
    rent_rows = (
        await db.execute(
            text(
                """
                SELECT
                    competencia,
                    tab_x_classe_serie  AS classe_serie,
                    tab_x_vl_rentab_mes AS rent
                FROM cvm_remote.tab_x_3
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia BETWEEN :inicio AND :fim
                ORDER BY competencia
                """
            ),
            params_range,
        )
    ).all()
    rent_map: dict[date, dict[str, float]] = {}
    for r in rent_rows:
        rent_map.setdefault(r.competencia, {})[str(r.classe_serie)] = _parse_num_text(
            r.rent
        )
    rent_serie = [
        RentPonto(competencia=comp, por_subclasse=mapa)
        for comp, mapa in sorted(rent_map.items())
    ]

    # -----------------------------------------------------------------
    # 13) rent_acumulada -- derivada, acumula (1 + rent/100) por subclasse
    # -----------------------------------------------------------------
    rent_acumulada: list[RentAcumuladaPonto] = []
    acum_por_sub: dict[str, float] = {}
    for ponto in rent_serie:
        for sub, rent_pct in ponto.por_subclasse.items():
            prev = acum_por_sub.get(sub, 1.0)
            acum_por_sub[sub] = prev * (1.0 + rent_pct / 100.0)
        snapshot = {
            sub: (acum - 1.0) * 100.0 for sub, acum in acum_por_sub.items()
        }
        rent_acumulada.append(
            RentAcumuladaPonto(
                competencia=ponto.competencia,
                por_subclasse=snapshot,
                cdi_acum=None,
            )
        )

    # -----------------------------------------------------------------
    # 14) desempenho_vs_meta -- tab_x_6 por subclasse/competencia
    # -----------------------------------------------------------------
    desemp_rows = (
        await db.execute(
            text(
                """
                SELECT
                    competencia,
                    tab_x_classe_serie       AS classe_serie,
                    tab_x_pr_desemp_esperado AS esperado,
                    tab_x_pr_desemp_real     AS real
                FROM cvm_remote.tab_x_6
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia BETWEEN :inicio AND :fim
                ORDER BY competencia
                """
            ),
            params_range,
        )
    ).all()
    desemp_map: dict[date, dict[str, DesempenhoGap]] = {}
    for r in desemp_rows:
        esp = _parse_num_text(r.esperado)
        realz = _parse_num_text(r.real)
        desemp_map.setdefault(r.competencia, {})[str(r.classe_serie)] = DesempenhoGap(
            esperado=esp, realizado=realz, gap=realz - esp
        )
    desempenho_vs_meta = [
        DesempenhoPonto(competencia=comp, por_subclasse=mapa)
        for comp, mapa in sorted(desemp_map.items())
    ]

    # -----------------------------------------------------------------
    # 15) liquidez_serie -- tab_x_5 (colunas text no CSV)
    # -----------------------------------------------------------------
    liq_rows = (
        await db.execute(
            text(
                """
                SELECT
                    competencia,
                    tab_x_vl_liquidez_0         AS d0,
                    tab_x_vl_liquidez_30        AS d30,
                    tab_x_vl_liquidez_60        AS d60,
                    tab_x_vl_liquidez_90        AS d90,
                    tab_x_vl_liquidez_180       AS d180,
                    tab_x_vl_liquidez_360       AS d360,
                    tab_x_vl_liquidez_maior_360 AS mais_360
                FROM cvm_remote.tab_x_5
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia BETWEEN :inicio AND :fim
                ORDER BY competencia
                """
            ),
            params_range,
        )
    ).all()
    liquidez_serie = [
        LiquidezPonto(
            competencia=r.competencia,
            faixas=LiquidezFaixas(
                d0=_parse_num_text(r.d0),
                d30=_parse_num_text(r.d30),
                d60=_parse_num_text(r.d60),
                d90=_parse_num_text(r.d90),
                d180=_parse_num_text(r.d180),
                d360=_parse_num_text(r.d360),
                mais_360=_parse_num_text(r.mais_360),
            ),
        )
        for r in liq_rows
    ]

    # -----------------------------------------------------------------
    # 16) fluxo_cotas -- tab_x_4, uma linha por combinacao
    # -----------------------------------------------------------------
    fluxo_rows = (
        await db.execute(
            text(
                """
                SELECT
                    competencia,
                    tab_x_tp_oper       AS tp_oper,
                    tab_x_classe_serie  AS classe_serie,
                    tab_x_vl_total      AS vl_total,
                    tab_x_qt_cota       AS qt_cota
                FROM cvm_remote.tab_x_4
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia BETWEEN :inicio AND :fim
                ORDER BY competencia, tab_x_classe_serie, tab_x_tp_oper
                """
            ),
            params_range,
        )
    ).all()
    fluxo_cotas = [
        FluxoCotasPonto(
            competencia=r.competencia,
            tp_oper=str(r.tp_oper or ""),
            classe_serie=str(r.classe_serie or ""),
            vl_total=_parse_num_text(r.vl_total),
            qt_cota=_parse_num_text(r.qt_cota),
        )
        for r in fluxo_rows
    ]

    # -----------------------------------------------------------------
    # 16b) recompra_serie -- Recompras de DC (Tabela VII.d)
    # Volume mensal (vl + qt + valor contabil) + %PL (cruza com tab_iv.a).
    # -----------------------------------------------------------------
    recompra_rows = (
        await db.execute(
            text(
                """
                SELECT competencia,
                       tab_vii_d_1_qt_recompra       AS qt,
                       tab_vii_d_2_vl_recompra       AS vl,
                       tab_vii_d_3_vl_contab_recompra AS vl_contab
                FROM cvm_remote.tab_vii
                WHERE cnpj_fundo_classe = :cnpj
                  AND competencia BETWEEN :inicio AND :fim
                ORDER BY competencia
                """
            ),
            params_range,
        )
    ).all()
    recompra_serie: list[RecompraPonto] = []
    for r in recompra_rows:
        vl_rec = _as_float(r.vl)
        pl_ref = pl_por_comp.get(r.competencia)
        pct_pl = (vl_rec / pl_ref * 100) if pl_ref and pl_ref > 0 else None
        recompra_serie.append(
            RecompraPonto(
                competencia=r.competencia,
                qt_recompra=_as_float(r.qt),
                vl_recompra=vl_rec,
                vl_contab_recompra=_as_float(r.vl_contab),
                pct_pl=pct_pl,
            )
        )

    # -----------------------------------------------------------------
    # 17) scr_distribuicao -- tab_x (valores, nao %), competencia atual
    # -----------------------------------------------------------------
    scr_row = (
        await db.execute(
            text(
                """
                SELECT
                    tab_x_scr_risco_devedor_aa AS aa,
                    tab_x_scr_risco_devedor_a  AS a,
                    tab_x_scr_risco_devedor_b  AS b,
                    tab_x_scr_risco_devedor_c  AS c,
                    tab_x_scr_risco_devedor_d  AS d,
                    tab_x_scr_risco_devedor_e  AS e,
                    tab_x_scr_risco_devedor_f  AS f,
                    tab_x_scr_risco_devedor_g  AS g,
                    tab_x_scr_risco_devedor_h  AS h
                FROM cvm_remote.tab_x
                WHERE cnpj_fundo_classe = :cnpj AND competencia = :comp
                """
            ),
            {"cnpj": cnpj_fmt, "comp": comp_atual},
        )
    ).one_or_none()

    scr_distribuicao: list[SCRLinha] = []
    if scr_row is not None:
        pares_scr = [
            ("AA", _parse_num_text(scr_row.aa)),
            ("A",  _parse_num_text(scr_row.a)),
            ("B",  _parse_num_text(scr_row.b)),
            ("C",  _parse_num_text(scr_row.c)),
            ("D",  _parse_num_text(scr_row.d)),
            ("E",  _parse_num_text(scr_row.e)),
            ("F",  _parse_num_text(scr_row.f)),
            ("G",  _parse_num_text(scr_row.g)),
            ("H",  _parse_num_text(scr_row.h)),
        ]
        total_scr = sum(v for _, v in pares_scr if v > 0)
        for rating, val in pares_scr:
            if val <= 0:
                continue
            pct = (val / total_scr * 100) if total_scr > 0 else 0.0
            scr_distribuicao.append(SCRLinha(rating=rating, valor=val, pct=pct))

    # -----------------------------------------------------------------
    # 18) garantias -- tab_x_7 competencia atual
    # -----------------------------------------------------------------
    gar_row = (
        await db.execute(
            text(
                """
                SELECT
                    tab_x_vl_garantia_dircred AS vl,
                    tab_x_pr_garantia_dircred AS pr
                FROM cvm_remote.tab_x_7
                WHERE cnpj_fundo_classe = :cnpj AND competencia = :comp
                """
            ),
            {"cnpj": cnpj_fmt, "comp": comp_atual},
        )
    ).one_or_none()

    garantias: Garantias | None = None
    if gar_row is not None:
        vl_g = _parse_num_text(gar_row.vl)
        pr_g = _parse_num_text(gar_row.pr)
        # CVM as vezes publica fracao 0..1, as vezes 0..100.
        pct_g = pr_g * 100 if 0 < pr_g <= 1 else pr_g
        if vl_g > 0 or pct_g > 0:
            garantias = Garantias(vl_garantia=vl_g, pct_garantia=pct_g)

    # -----------------------------------------------------------------
    # Monta resposta + proveniencia na competencia atual.
    # -----------------------------------------------------------------
    ficha = FichaFundo(
        identificacao=identificacao,
        pl_serie=pl_serie,
        carteira_serie=carteira_serie,
        atraso_serie=atraso_serie,
        prazo_medio_serie=prazo_medio_serie,
        cedentes=cedentes,
        setores=setores,
        subclasses=subclasses,
        cotistas_serie=cotistas_serie,
        cotistas_tipo_serie=cotistas_tipo_serie,
        pl_subclasses_serie=pl_subclasses_serie,
        rent_serie=rent_serie,
        rent_acumulada=rent_acumulada,
        desempenho_vs_meta=desempenho_vs_meta,
        liquidez_serie=liquidez_serie,
        fluxo_cotas=fluxo_cotas,
        recompra_serie=recompra_serie,
        scr_distribuicao=scr_distribuicao,
        garantias=garantias,
        limitacoes=list(_LIMITACOES_FICHA),
    )
    return ficha, await _build_provenance(db, comp_atual)
