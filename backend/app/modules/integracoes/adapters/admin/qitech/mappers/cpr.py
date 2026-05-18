"""Mapper: payload /netreport/report/market/cpr/{data} -> dict canonico.

source_id = `{clienteId}|{data_iso}|sha16(descricao+valor)` -- usa SOMENTE
campos identificadores estaveis. Antes (v0.2.x): sha do item dict inteiro,
mas a QiTech inclui campos derivados (percentuais sobre CPR/total) que
mudam entre fetches mesmo quando o evento e o mesmo, gerando source_ids
diferentes e duplicatas em upsert. Corrigido em v0.3.0 (2026-05-18) apos
14 duplicatas serem observadas em REALINVEST 2026-05-13.

Risco residual: dois CPRs distintos com mesma (descricao, valor) no mesmo
dia/cliente colidem em 1 row. Aceitavel — eventos sao identificados pelo
gestor por descricao+valor, dupla legitima e rara.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.admin.qitech.mappers._common import (
    build_provenance,
    parse_iso_or_none,
    to_decimal,
)


def map_cpr(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    data_posicao: date,
) -> list[dict[str, Any]]:
    relatorios = payload.get("relatórios") if isinstance(payload, dict) else None
    if not isinstance(relatorios, dict):
        return []

    items = relatorios.get("cpr")
    if not isinstance(items, list) or not items:
        return []

    ingested_at = datetime.now(UTC)
    data_iso = data_posicao.isoformat()
    rows: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        cliente_id = str(item.get("clienteId", ""))
        # Hash estavel: so descricao + valor (campos identificadores).
        # Ignora percentualSobreCpr/Total (derivados, mudam entre fetches).
        descricao = str(item.get("descrição", ""))
        valor_str = str(to_decimal(item.get("valor")))
        stable_key = f"{descricao}|{valor_str}"
        item_hash = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()
        source_id = f"{cliente_id}|{data_iso}|{item_hash[:16]}"

        rows.append(
            {
                "tenant_id": tenant_id,
                "data_posicao": data_posicao,
                "carteira_cliente_id": cliente_id,
                "carteira_cliente_nome": str(item.get("clienteNome", "")),
                "carteira_cliente_doc": str(item.get("cpfDoCliente", "")),
                "descricao": descricao,
                "historico_traduzido": str(item.get("históricoTraduzido", "")),
                "valor": to_decimal(item.get("valor")),
                "percentual_sobre_cpr": to_decimal(item.get("percentualSobreCpr")),
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
