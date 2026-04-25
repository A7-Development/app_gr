"""Mapper: payload /netreport/report/market/demonstrativo-caixa/{data} -> dict canonico.

QiTech NAO devolve id estavel — pode ter dois lancamentos com mesma
descricao no mesmo dia (ex.: 2 resgates de mesmo fundo). Por isso o
`source_id` inclui sha16 do payload do item: garante unicidade.

source_id = `{clienteId}|{YYYY-MM-DD}|{sha16(item)}`.

Trade-off documentado: se a QiTech corrigir um typo numa descricao, a row
canonica vira nova linha em vez de update. Aceitavel pra MVP.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.admin.qitech.hashing import sha256_of_row
from app.modules.integracoes.adapters.admin.qitech.mappers._common import (
    build_provenance,
    normalize_str_or_none,
    parse_iso_or_none,
    to_decimal,
)


def _to_int_or_none(value: Any) -> int | None:
    """idConta vem `0` ou `null`. Caller decide se 0 e legitimo."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def map_demonstrativo_caixa(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    data_posicao: date,
) -> list[dict[str, Any]]:
    relatorios = payload.get("relatórios") if isinstance(payload, dict) else None
    if not isinstance(relatorios, dict):
        return []

    items = relatorios.get("demonstrativo-caixa")
    if not isinstance(items, list) or not items:
        return []

    ingested_at = datetime.now(UTC)
    data_iso = data_posicao.isoformat()
    rows: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        cliente_id = str(item.get("clienteId", ""))
        # data_liquidacao do payload (pode diferir do data_posicao se
        # for movimento futuro/passado relatado).
        dt_liq = parse_iso_or_none(item.get("dataLiquidação"))
        data_liquidacao = dt_liq.date() if dt_liq else data_posicao

        item_hash = sha256_of_row(item)
        # Composicao: clienteId + data_posicao da fetch + sha16 do item.
        # data_posicao (param) garante que re-rodar o mesmo dia nao colide
        # com movimentos de dias diferentes que tenham mesmo conteudo.
        source_id = f"{cliente_id}|{data_iso}|{item_hash[:16]}"

        rows.append(
            {
                "tenant_id": tenant_id,
                "data_liquidacao": data_liquidacao,
                "carteira_cliente_id": cliente_id,
                "carteira_cliente_nome": str(item.get("clienteNome", "")),
                "carteira_cliente_doc": str(item.get("cpfDoCliente", "")),
                "tipo_de_registro": int(item.get("tipoDeRegistro", 0)),
                "descricao": str(item.get("descrição", "")),
                "historico_traduzido": str(item.get("históricoTraduzido", "")),
                "banco": normalize_str_or_none(item.get("banco")),
                "agencia": normalize_str_or_none(item.get("agencia")),
                "conta_corrente": normalize_str_or_none(item.get("contaCorrente")),
                "digito": normalize_str_or_none(item.get("digito")),
                "id_conta": _to_int_or_none(item.get("idConta")),
                "conta_investimento": normalize_str_or_none(
                    item.get("contaInvestimento")
                ),
                "entradas": to_decimal(item.get("entradas")),
                "saidas": to_decimal(item.get("saídas")),
                "saldo": to_decimal(item.get("saldo")),
                **build_provenance(
                    source_id=source_id,
                    item=item,
                    ingested_at=ingested_at,
                    source_updated_at=dt_liq,
                ),
            }
        )

    return rows
