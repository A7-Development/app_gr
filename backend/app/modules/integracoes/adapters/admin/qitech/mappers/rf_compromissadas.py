"""Mapper: payload /netreport/report/market/rf-compromissadas/{data} -> dict canonico.

Compromissada = RF overnight tipico. Schema parecido com `rf` mas SEM
emitente/cnpj_emitente, com pares dataAquisicao/dataResgate.

source_id = `{clienteId}|{codigo}|{YYYY-MM-DD}`.
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
    dt = parse_iso_or_none(value)
    return dt.date() if dt else None


def map_rf_compromissadas(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    data_posicao: date,
) -> list[dict[str, Any]]:
    relatorios = payload.get("relatórios") if isinstance(payload, dict) else None
    if not isinstance(relatorios, dict):
        return []

    items = relatorios.get("rf-compromissadas")
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
                "carteira_cliente_id": cliente_id,
                "carteira_cliente_nome": str(item.get("clienteNome", "")),
                "carteira_cliente_doc": str(item.get("cpfDoCliente", "")),
                "codigo": codigo,
                "papel": str(item.get("papel", "")),
                "data_aquisicao": _parse_date_or_none(
                    item.get("dataAquisição")
                ),
                "data_resgate": _parse_date_or_none(item.get("dataResgate")),
                "data_emissao": _parse_date_or_none(item.get("dataEmissão")),
                "data_vencimento": _parse_date_or_none(
                    item.get("dataVencimento")
                ),
                "taxa_over": to_decimal(item.get("taxaOver")),
                "taxa_ano": to_decimal(item.get("taxaAno")),
                "quantidade": to_decimal(item.get("quantidade")),
                "pu": to_decimal(item.get("pu")),
                "valor_aplicado": to_decimal(item.get("valorAplicado")),
                "valor_resgate": to_decimal(item.get("valorResgate")),
                "valor_bruto": to_decimal(item.get("valorBruto")),
                "percentual_sobre_rf": to_decimal(
                    item.get("percentualSobreRf")
                ),
                "percentual_sobre_total": to_decimal(
                    item.get("percentualSobreTotal")
                ),
                "mtm": normalize_str_or_none(item.get("mtm")),
                "negociacao_vencimento": normalize_str_or_none(
                    item.get("negociação/vencimento")
                ),
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
