"""Mapper: payload /netreport/report/market/mec/{data} -> dict canonico.

source_id = `{clienteId}|{YYYY-MM-DD}` (cada `clienteId` representa uma
classe de cota distinta).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.admin.qitech.mappers._common import (
    build_provenance,
    parse_iso_or_none,
    to_decimal,
)


def map_mec(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    data_posicao: date,
) -> list[dict[str, Any]]:
    relatorios = payload.get("relatórios") if isinstance(payload, dict) else None
    if not isinstance(relatorios, dict):
        return []

    items = relatorios.get("mec")
    if not isinstance(items, list) or not items:
        return []

    ingested_at = datetime.now(UTC)
    data_iso = data_posicao.isoformat()
    rows: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        cliente_id = str(item.get("clienteId", ""))
        source_id = f"{cliente_id}|{data_iso}"

        rows.append(
            {
                "tenant_id": tenant_id,
                "data_posicao": data_posicao,
                "carteira_cliente_id": cliente_id,
                "carteira_cliente_nome": str(item.get("clienteNome", "")),
                "carteira_cliente_doc": str(item.get("cpfDoCliente", "")),
                "entradas": to_decimal(item.get("entradas")),
                "saidas": to_decimal(item.get("saidas")),
                "aporte": to_decimal(item.get("aporte")),
                "retirada": to_decimal(item.get("retirada")),
                "patrimonio": to_decimal(item.get("patrimonio")),
                "quantidade": to_decimal(item.get("quantidade")),
                "valor_da_cota": to_decimal(item.get("valorDaCota")),
                "variacao_diaria": to_decimal(item.get("variaçãoDiaria")),
                "variacao_mensal": to_decimal(item.get("variaçãoMensal")),
                "variacao_anual": to_decimal(item.get("variaçãoAnual")),
                "variacao_total": to_decimal(item.get("variaçãoTotal")),
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
