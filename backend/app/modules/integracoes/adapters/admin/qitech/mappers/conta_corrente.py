"""Mapper: payload /netreport/report/market/conta-corrente/{data} -> dict canonico.

Granularidade: 1 linha por (tenant, data, codigo_conta, cliente). source_id =
`{clienteId}|{codigo}|{YYYY-MM-DD}`.

Payload (forma observada):

    {
      "relatorios": {
        "conta-corrente": [
          {
            "dataDaPosicao": "2026-01-13T...",
            "codigo": "BRADESCO",
            "descricao": "CC - BRADESCO",
            "instituicao": "BRADESCO",
            "valorTotal": 13671.59,
            "percentualSobreContaCorrente": 0,
            "percentualSobreTotal": 0.13,
            "cpfDoCliente": "42449234000160",
            "clienteNome": "REALINVEST FIDC",
            "clienteId": "REALINVEST"
          },
          ...
        ]
      },
      "_links": {...}
    }
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.admin.qitech.mappers._common import (
    build_provenance,
    parse_iso_or_none,
    to_decimal,
    to_decimal_or_none_within,
)

# Teto absoluto dos campos NUMERIC(8,4) no schema canonico.
_PCT_MAX_ABS = Decimal("9999.9999")


def map_conta_corrente(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    data_posicao: date,
) -> list[dict[str, Any]]:
    """Transforma payload QiTech em linhas pra `wh_saldo_conta_corrente`."""
    relatorios = payload.get("relatórios") if isinstance(payload, dict) else None
    if not isinstance(relatorios, dict):
        return []

    items = relatorios.get("conta-corrente")
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
                # Conta
                "codigo": codigo,
                "descricao": str(item.get("descrição", "")),
                "instituicao": str(item.get("instituição", "")),
                # Fatos
                "valor_total": to_decimal(item.get("valorTotal")),
                # Pct podem vir como lixo (~1e18) quando o saldo liquido da
                # carteira e zero — clampamos pra None pra nao estourar o
                # NUMERIC(8,4). Ver `to_decimal_or_none_within` em _common.
                "percentual_sobre_conta_corrente": to_decimal_or_none_within(
                    item.get("percentualSobreContaCorrente"),
                    max_abs=_PCT_MAX_ABS,
                ),
                "percentual_sobre_total": to_decimal_or_none_within(
                    item.get("percentualSobreTotal"),
                    max_abs=_PCT_MAX_ABS,
                ),
                # Proveniencia
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
