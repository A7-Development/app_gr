"""QiTech endpoint coverage resolver.

Pra cada endpoint diario da QiTech, retorna a lista de datas presentes
nas raw tables (com http_status). Usado pelo `/coverage` da UI pra
distinguir 'ok' / 'not_published' / 'gap'.

Escopo Fase 1: somente endpoints DAILY_AT que tem 1 linha raw por
data_posicao. Endpoints INTERVAL (statement) e ON_DEMAND (fidc_estoque)
sao retornados como `supported=False` — a UI mostra placeholder.
"""

from __future__ import annotations

from datetime import date
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CoverageRow(NamedTuple):
    """Uma linha de cobertura: (data, http_status). http_status=None quando
    nao existe linha raw — a UI decide se eh gap, weekend, etc."""

    data_posicao: date
    http_status: int | None


# Endpoint name → (tabela_raw, coluna_de_tipo, valor_de_tipo).
# Quando coluna_de_tipo eh None, a tabela inteira pertence ao endpoint.
_QITECH_MARKET_ENDPOINTS: dict[str, tuple[str, str | None, str | None]] = {
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
    "bank_account.balance": ("wh_qitech_raw_bank_account_balance", None, None),
}


# Endpoints sem suporte a coverage diaria nesta fase. Devolvido com
# `supported=False` pra UI renderizar placeholder.
_QITECH_UNSUPPORTED_FOR_COVERAGE = frozenset(
    {
        # INTERVAL — dado continuo, coverage por dia eh ambigua.
        "bank_account.statement",
        # ON_DEMAND — disparado por job, sem cadencia diaria.
        "market.fidc_estoque",
    }
)


def qitech_endpoint_supports_coverage(endpoint_name: str) -> bool:
    """Returns True if this endpoint has 1-row-per-day raw layout."""
    return endpoint_name in _QITECH_MARKET_ENDPOINTS


async def fetch_qitech_coverage(
    db: AsyncSession,
    *,
    endpoint_name: str,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    start_date: date,
    end_date: date,
) -> list[CoverageRow]:
    """Para um endpoint QiTech, devolve as linhas raw entre [start, end].

    Cada linha tem (data_posicao, http_status). A UI cruza com calendar
    pra decidir 'gap' vs 'weekend' vs 'holiday'.
    """
    if endpoint_name not in _QITECH_MARKET_ENDPOINTS:
        return []

    table, type_col, type_val = _QITECH_MARKET_ENDPOINTS[endpoint_name]

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

    sql = text(
        f"""
        SELECT data_posicao, http_status
        FROM {table}
        WHERE {" AND ".join(where)}
        """
    )
    result = await db.execute(sql, params)
    return [CoverageRow(data_posicao=r[0], http_status=r[1]) for r in result.all()]
