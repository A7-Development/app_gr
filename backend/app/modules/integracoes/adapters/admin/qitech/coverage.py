"""QiTech endpoint coverage resolver.

Pra cada endpoint da QiTech, retorna a lista de datas presentes nas raw
tables com http_status. Usado pelo `/coverage` da UI pra distinguir 'ok' /
'not_published' / 'gap'.

3 layouts de raw cobertos:

- **Per-day report** (`wh_qitech_raw_relatorio`): 1 linha por (tipo, data_posicao).
  Cobre 10 endpoints `market.*` SYNC + `market.fidc_estoque` (ON_DEMAND mas
  semantica diaria — disparada pra uma data_posicao especifica).

- **Per-day balance** (`wh_qitech_raw_bank_account_balance`): 1 linha por
  data_posicao. Cobre `bank_account.balance`.

- **Range overlap** (`wh_qitech_raw_bank_account_statement`): 1 linha por
  (periodo_inicio, periodo_fim). Cobertura diaria = "a data caiu dentro de
  algum periodo coletado". Cobre `bank_account.statement` (INTERVAL).

Todos os endpoints do catalogo QiTech tem suporte a coverage — ON_DEMAND e
INTERVAL inclusos. O conceito muda mas a pergunta e a mesma: "que dias
estao populados na canonica?".
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CoverageRow(NamedTuple):
    """Uma linha de cobertura: (data, http_status, completeness).

    `http_status=None` quando nao existe linha raw — a UI decide se eh gap,
    weekend, etc. `completeness` so se aplica a tabelas raw que tem a coluna
    (hoje so `wh_qitech_raw_relatorio`); demais tabelas devolvem None."""

    data_posicao: date
    http_status: int | None
    completeness: str | None = None


# Per-day endpoints: { endpoint_name: (tabela, type_col, type_value) }.
# type_col=None significa "tabela inteira pertence a este endpoint".
#
# Custodia.* (2026-05-13): adicionados depois — gravam em wh_qitech_raw_relatorio
# com tipo_de_mercado='fidc-custodia/<nome>' e data_posicao=data_referencia
# (data_final pros range, data_importacao pro detalhes, hoje UTC pro snapshot
# de movimento_aberto). 1 raw por dia de disparo do sync, cabe no padrao
# per-day. Antes de adicionar aqui, esses 4 endpoints apareciam cinza vazio
# (`supported=False`) no heatmap — bug observacional do PR original da aba
# Cobertura (commit 75968e7).
_PER_DAY_ENDPOINTS: dict[str, tuple[str, str | None, str | None]] = {
    "market.outros_fundos": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "outros-fundos"),
    "market.conta_corrente": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "conta-corrente"),
    "market.tesouraria": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "tesouraria"),
    "market.outros_ativos": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "outros-ativos"),
    "market.demonstrativo_caixa": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "demonstrativo-caixa"),
    "market.cpr": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "cpr"),
    "market.mec": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "mec"),
    "market.rentabilidade": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "rentabilidade"),
    "market.rf": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "rf"),
    "market.rf_compromissadas": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "rf-compromissadas"),
    "market.fidc_estoque": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "fidc-estoque"),
    "custodia.aquisicao_consolidada": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "fidc-custodia/aquisicao-consolidada"),
    "custodia.liquidados_baixados": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "fidc-custodia/liquidados-baixados"),
    "custodia.movimento_aberto": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "fidc-custodia/movimento-aberto"),
    "custodia.detalhes_operacoes": ("wh_qitech_raw_relatorio", "tipo_de_mercado", "fidc-custodia/detalhes-operacoes"),
    "bank_account.balance": ("wh_qitech_raw_bank_account_balance", None, None),
}


# Range-overlap endpoints: usam (periodo_inicio, periodo_fim) — a expansao
# em datas diarias acontece em Python (mais simples que SQL generate_series
# dinamico, sem custo perceptivel pra ranges de ate ~730 dias).
_RANGE_OVERLAP_ENDPOINTS: dict[str, str] = {
    "bank_account.statement": "wh_qitech_raw_bank_account_statement",
}


def qitech_endpoint_supports_coverage(endpoint_name: str) -> bool:
    """Todos os endpoints QiTech tem alguma forma de coverage."""
    return (
        endpoint_name in _PER_DAY_ENDPOINTS
        or endpoint_name in _RANGE_OVERLAP_ENDPOINTS
    )


async def fetch_qitech_coverage(
    db: AsyncSession,
    *,
    endpoint_name: str,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    start_date: date,
    end_date: date,
) -> list[CoverageRow]:
    """Devolve linhas (data, http_status) cobertas pra um endpoint QiTech."""
    if endpoint_name in _PER_DAY_ENDPOINTS:
        return await _fetch_per_day(
            db,
            spec=_PER_DAY_ENDPOINTS[endpoint_name],
            tenant_id=tenant_id,
            unidade_administrativa_id=unidade_administrativa_id,
            start_date=start_date,
            end_date=end_date,
        )
    if endpoint_name in _RANGE_OVERLAP_ENDPOINTS:
        return await _fetch_range_overlap(
            db,
            table=_RANGE_OVERLAP_ENDPOINTS[endpoint_name],
            tenant_id=tenant_id,
            unidade_administrativa_id=unidade_administrativa_id,
            start_date=start_date,
            end_date=end_date,
        )
    return []


async def fetch_qitech_first_data_date(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
) -> date | None:
    """MIN(data_posicao) cross-endpoint — usado pra resolver 'todo o periodo'."""
    where_ua = ""
    params: dict[str, object] = {"tenant_id": tenant_id}
    if unidade_administrativa_id is not None:
        where_ua = "AND unidade_administrativa_id = :ua_id"
        params["ua_id"] = unidade_administrativa_id

    sql = text(
        f"""
        SELECT MIN(d) FROM (
            SELECT MIN(data_posicao) AS d
            FROM wh_qitech_raw_relatorio
            WHERE tenant_id = :tenant_id {where_ua}
            UNION ALL
            SELECT MIN(data_posicao) AS d
            FROM wh_qitech_raw_bank_account_balance
            WHERE tenant_id = :tenant_id {where_ua}
            UNION ALL
            SELECT MIN(periodo_inicio) AS d
            FROM wh_qitech_raw_bank_account_statement
            WHERE tenant_id = :tenant_id {where_ua}
        ) s
        """
    )
    result = await db.execute(sql, params)
    return result.scalar_one_or_none()


async def _fetch_per_day(
    db: AsyncSession,
    *,
    spec: tuple[str, str | None, str | None],
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    start_date: date,
    end_date: date,
) -> list[CoverageRow]:
    table, type_col, type_val = spec
    where = ["tenant_id = :tenant_id", "data_posicao BETWEEN :start AND :end"]
    params: dict[str, object] = {
        "tenant_id": tenant_id,
        "start": start_date,
        "end": end_date,
    }
    if type_col is not None and type_val is not None:
        where.append(f"{type_col} = :type_val")
        params["type_val"] = type_val
    if unidade_administrativa_id is not None:
        where.append("unidade_administrativa_id = :ua_id")
        params["ua_id"] = unidade_administrativa_id

    # `completeness` so existe em wh_qitech_raw_relatorio (migration
    # e4a7b2c9d031). Para outras tabelas (ex.: wh_qitech_raw_bank_account_*)
    # devolvemos NULL — UI trata como "sem semantica de completeness".
    select_completeness = (
        "completeness" if table == "wh_qitech_raw_relatorio" else "NULL"
    )
    sql = text(
        f"""
        SELECT data_posicao, http_status, {select_completeness} AS completeness
        FROM {table}
        WHERE {" AND ".join(where)}
        """
    )
    result = await db.execute(sql, params)
    return [
        CoverageRow(data_posicao=r[0], http_status=r[1], completeness=r[2])
        for r in result.all()
    ]


async def _fetch_range_overlap(
    db: AsyncSession,
    *,
    table: str,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    start_date: date,
    end_date: date,
) -> list[CoverageRow]:
    """Pra cada linha raw com (periodo_inicio, periodo_fim), expande pras datas
    individuais dentro do range. Quando varias rows cobrem a mesma data,
    mantem o MELHOR http_status (200 ganha de 4xx)."""
    where = [
        "tenant_id = :tenant_id",
        "periodo_inicio <= :end",
        "periodo_fim >= :start",
    ]
    params: dict[str, object] = {
        "tenant_id": tenant_id,
        "start": start_date,
        "end": end_date,
    }
    if unidade_administrativa_id is not None:
        where.append("unidade_administrativa_id = :ua_id")
        params["ua_id"] = unidade_administrativa_id

    sql = text(
        f"""
        SELECT periodo_inicio, periodo_fim, http_status
        FROM {table}
        WHERE {" AND ".join(where)}
        """
    )
    result = await db.execute(sql, params)

    by_date: dict[date, int | None] = {}
    for inicio, fim, http_status in result.all():
        cursor = max(inicio, start_date)
        end_loop = min(fim, end_date)
        while cursor <= end_loop:
            existing = by_date.get(cursor)
            # Mantem o melhor: 200 < 400 < None. Se algum status veio 200
            # pra esta data, ela conta como ok mesmo que outra row tenha 4xx.
            if existing is None or (
                http_status is not None and http_status < (existing or 999)
            ):
                by_date[cursor] = http_status
            cursor = cursor + timedelta(days=1)

    # bank_account_statement nao tem coluna completeness — devolvemos None.
    return [
        CoverageRow(data_posicao=d, http_status=s, completeness=None)
        for d, s in by_date.items()
    ]
