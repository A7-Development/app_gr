"""Mapper: payload /netreport/report/market/rentabilidade/{data} -> dict canonico.

source_id = `{clienteId}|{indexador}|{YYYY-MM-DD}`. Cada indexador
(PATRIMON, COTA, CDI, SEL, DOL, IBOV FEC, IGPM, etc) e uma linha por
classe de cota.

Nullables: cada indexador preenche um subset das metricas:
- PATRIMON so preenche `valor_patrimonio`.
- COTA preenche todas as `rentabilidade_*` mas nenhuma `percentual_*`.
- CDI/SEL/DOL/etc preenchem `percentual_bench_mark` + `rentabilidade_real`
  + as demais rentabilidades.

`to_decimal_or_none` preserva NULL quando o campo nao se aplica (em vez
de virar zero, o que falsearia o dado).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.admin.qitech.mappers._common import (
    build_provenance,
    normalize_str_or_none,
    parse_iso_or_none,
    to_decimal_or_none,
)


def map_rentabilidade(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    data_posicao: date,
) -> list[dict[str, Any]]:
    relatorios = payload.get("relatórios") if isinstance(payload, dict) else None
    if not isinstance(relatorios, dict):
        return []

    items = relatorios.get("rentabilidade")
    if not isinstance(items, list) or not items:
        return []

    ingested_at = datetime.now(UTC)
    data_iso = data_posicao.isoformat()
    rows: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        cliente_id = str(item.get("clienteId", ""))
        indexador = str(item.get("indexador", ""))
        source_id = f"{cliente_id}|{indexador}|{data_iso}"

        rows.append(
            {
                "tenant_id": tenant_id,
                "data_posicao": data_posicao,
                "carteira_cliente_id": cliente_id,
                "carteira_cliente_nome": str(item.get("clienteNome", "")),
                "carteira_cliente_doc": str(item.get("cpfDoCliente", "")),
                "indexador": indexador,
                "percentual_bench_mark": to_decimal_or_none(
                    item.get("percentualBenchMark")
                ),
                "rentabilidade_real": to_decimal_or_none(
                    item.get("rentabilidadeReal")
                ),
                "rentabilidade_diaria": to_decimal_or_none(
                    item.get("rentabilidadeDiária")
                ),
                "rentabilidade_mensal": to_decimal_or_none(
                    item.get("rentabilidadeMensal")
                ),
                "rentabilidade_anual": to_decimal_or_none(
                    item.get("rentabilidadeAnual")
                ),
                "rentabilidade_6_meses": to_decimal_or_none(
                    item.get("rentabilidade6Meses")
                ),
                "rentabilidade_12_meses": to_decimal_or_none(
                    item.get("rentabilidade12Meses")
                ),
                "valor_patrimonio": to_decimal_or_none(
                    item.get("valorPatrimonio")
                ),
                "codigo_isin": normalize_str_or_none(item.get("códigoIsin")),
                "percentual_6_meses": to_decimal_or_none(
                    item.get("percentual6Meses")
                ),
                "percentual_12_meses": to_decimal_or_none(
                    item.get("percentual12Meses")
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
