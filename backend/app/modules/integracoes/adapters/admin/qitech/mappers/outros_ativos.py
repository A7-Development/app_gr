"""Mapper: payload /netreport/report/market/outros-ativos/{data} -> dict canonico.

source_id = `{clienteId}|{codigo}|{YYYY-MM-DD}`.
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


def map_outros_ativos(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    data_posicao: date,
) -> list[dict[str, Any]]:
    relatorios = payload.get("relatórios") if isinstance(payload, dict) else None
    if not isinstance(relatorios, dict):
        return []

    items = relatorios.get("outros-ativos")
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
                "descricao": str(item.get("descrição", "")),
                "tipo_do_ativo": str(item.get("tipoDoAtivo", "")),
                "descricao_tipo_de_ativo": str(
                    item.get("descriçãoTipoDeAtivo", "")
                ),
                "valor_total": to_decimal(item.get("valorTotal")),
                "percentual_sobre_outros_ativos": to_decimal(
                    item.get("percentualSobreOutrosAtivos")
                ),
                "percentual_sobre_total": to_decimal(
                    item.get("percentualSobreTotal")
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
