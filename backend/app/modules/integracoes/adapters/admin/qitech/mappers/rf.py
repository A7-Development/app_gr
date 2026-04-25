"""Mapper: payload /netreport/report/market/rf/{data} -> dict canonico.

source_id = `{clienteId}|{codigo}|{YYYY-MM-DD}`. `codigo` na QiTech e o
codigo interno da operacao (ex.: "C274830", "B811154") — unico por
posicao + data.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.admin.qitech.mappers._common import (
    build_provenance,
    normalize_str_or_none,
    parse_iso_or_none,
    to_decimal,
)


def _parse_date_or_none(value: Any) -> date | None:
    """Extrai apenas a data (sem TZ) de um ISO-8601 da QiTech."""
    dt = parse_iso_or_none(value)
    return dt.date() if dt else None


def map_rf(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    data_posicao: date,
) -> list[dict[str, Any]]:
    relatorios = payload.get("relatórios") if isinstance(payload, dict) else None
    if not isinstance(relatorios, dict):
        return []

    items = relatorios.get("rf")
    if not isinstance(items, list) or not items:
        return []

    ingested_at = datetime.now(UTC)
    data_iso = data_posicao.isoformat()
    rows: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        cliente_id = str(item.get("clienteId", ""))
        codigo = str(item.get("código", ""))
        source_id = f"{cliente_id}|{codigo}|{data_iso}"

        rows.append(
            {
                "tenant_id": tenant_id,
                "data_posicao": data_posicao,
                # Carteira
                "carteira_cliente_id": cliente_id,
                "carteira_cliente_nome": str(item.get("clienteNome", "")),
                "carteira_cliente_doc": str(item.get("cpfDoCliente", "")),
                # Ativo
                "codigo": codigo,
                "nome_do_papel": str(item.get("nomeDoPapel", "")),
                "emitente": str(item.get("Emitente", "")),
                "cnpj_emitente": str(item.get("cnpjEmitente", "")),
                "codigo_lastro": str(item.get("códigoLastro", "")),
                "indexador": str(item.get("indexador", "")),
                # Datas
                "data_da_emissao": _parse_date_or_none(
                    item.get("dataDaEmissão")
                ),
                "data_aplicacao": _parse_date_or_none(item.get("dataAplicação")),
                "data_vencimento": _parse_date_or_none(
                    item.get("dataVencimento")
                ),
                "data_vencimento_lastro": _parse_date_or_none(
                    item.get("dataVencimentoLastro")
                ),
                # Flags
                "origem": normalize_str_or_none(item.get("origem")),
                "operacao_a_termo": normalize_str_or_none(
                    item.get("operaçãoATermo")
                ),
                "negociacao_vencimento": normalize_str_or_none(
                    item.get("negociação/vencimento")
                ),
                # Taxas
                "taxa_mtm": to_decimal(item.get("taxaMTM")),
                "taxa_over": to_decimal(item.get("taxaOver")),
                "taxa_ano": to_decimal(item.get("taxaAno")),
                # Quantidades / PU
                "quantidade": to_decimal(item.get("quantidade")),
                "pu_mercado": to_decimal(item.get("puMercado")),
                # Valores
                "valor_aplicado": to_decimal(item.get("valorAplicado")),
                "valor_resgate": to_decimal(item.get("valorResgate")),
                "valor_bruto": to_decimal(item.get("valorBruto")),
                "valor_impostos": to_decimal(item.get("valorImpostos")),
                "valor_liquido": to_decimal(item.get("valorLíquido")),
                "percentual_sobre_rf": to_decimal(
                    item.get("percentualSobreRF")
                ),
                "percentual_sobre_total": to_decimal(
                    item.get("percentualSobreTotal")
                ),
                "mtm": normalize_str_or_none(item.get("mtm")),
                **build_provenance(
                    source_id=source_id,
                    item=item,
                    ingested_at=ingested_at,
                    source_updated_at=parse_iso_or_none(
                        item.get("dataDaPosição")
                    ),
                ),
            }
        )

    return rows
