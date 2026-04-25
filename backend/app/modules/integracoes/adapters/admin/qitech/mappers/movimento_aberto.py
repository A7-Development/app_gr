"""Mapper: /v2/fidc-custodia/report/movimento-aberto/{cnpj}/.

Wrapper: `{movimentoAberto: [...]}`. Snapshot atual de cessoes em aberto
(pendentes de liquidacao) do FIDC.

Schema baseado em spec passada pelo user em 2026-04-25 — sample real
veio vazio. Quando aparecer dado real, validar tipos e ajustar mapper se
necessario.

source_id = `{cnpj_fundo}|{seuNumero}|{numeroDocumento}|abt|{data_ref_iso}` —
inclui data_referencia (data da fetch) porque e snapshot diario; cada dia
gera um novo conjunto de linhas.
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
from app.modules.integracoes.adapters.admin.qitech.mappers.aquisicao_consolidada import (
    _normalize_cnpj_any,
)


def map_movimento_aberto(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    cnpj_fundo: str,
    data_referencia: date,
) -> list[dict[str, Any]]:
    """Transforma payload em linhas pra `wh_movimento_aberto`."""
    items = (
        payload.get("movimentoAberto") if isinstance(payload, dict) else None
    )
    if not isinstance(items, list) or not items:
        return []

    cnpj_fundo_norm = _normalize_cnpj_any(cnpj_fundo)
    ingested_at = datetime.now(UTC)
    data_iso = data_referencia.isoformat()
    rows: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        # seuNumero pode vir como integer no spec — normalizamos pra string.
        seu_numero = str(item.get("seuNumero", ""))
        numero_documento = str(item.get("numeroDocumento", ""))

        source_id = (
            f"{cnpj_fundo_norm}|{seu_numero}|{numero_documento}|abt|{data_iso}"
        )

        dt_movimento = parse_iso_or_none(item.get("dataMovimento"))
        dt_vencimento = parse_iso_or_none(item.get("dataVencimento"))

        rows.append(
            {
                "tenant_id": tenant_id,
                "data_referencia": data_referencia,
                "data_movimento": dt_movimento.date() if dt_movimento else None,
                "data_vencimento": dt_vencimento.date() if dt_vencimento else None,
                # Fundo
                "fundo_doc": _normalize_cnpj_any(item.get("docFundo")) or cnpj_fundo_norm,
                "fundo_nome": str(item.get("nomeFundo", "")),
                # Recebivel
                "seu_numero": seu_numero,
                "numero_documento": numero_documento,
                "tipo_movimento": str(item.get("tipoMovimento", "")),
                # Fatos
                "valor_aquisicao": to_decimal(item.get("valorAquisicao")),
                "valor_nominal": to_decimal(item.get("valorNominal")),
                "valor_movimentacao": to_decimal(item.get("valorMovimentacao")),
                # Proveniencia
                **build_provenance(
                    source_id=source_id,
                    item=item,
                    ingested_at=ingested_at,
                    source_updated_at=dt_movimento,
                ),
            }
        )

    return rows
