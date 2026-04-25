"""Mapper: /v2/fidc-custodia/report/fundo/{cnpj}/data/{data}.

Lista DIRETA (sem wrapper) de operacoes de remessa CNAB processadas no
dia. Cada item = 1 lote (arquivo .rem) que o cedente enviou.

source_id = `{cnpj_fundo}|{idOperacaoRecebivel}|rem`.

Diferente dos outros endpoints `fidc-custodia` (granularidade por
recebivel), aqui granularidade e por LOTE/operacao — varios recebiveis
agregados em 1 linha de remessa.
"""

from __future__ import annotations

from datetime import UTC, datetime
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


def _parse_bool_sim_nao(value: Any) -> bool:
    """SIM (case-insensitive) -> True; demais -> False."""
    if not value:
        return False
    return str(value).strip().upper() == "SIM"


def map_detalhes_operacoes(
    *,
    payload: list[dict[str, Any]] | dict[str, Any],
    tenant_id: UUID,
    cnpj_fundo: str,
) -> list[dict[str, Any]]:
    """Transforma payload em linhas pra `wh_operacao_remessa`.

    Aceita lista direta (formato observado) ou dict com wrapper (defensivo
    se a QiTech mudar a forma futuramente).
    """
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        # Defensivo: se algum dia vier wrapped.
        items_candidate = payload.get("detalhesOperacoes") or payload.get(
            "operacoes"
        )
        items = items_candidate if isinstance(items_candidate, list) else []
    else:
        return []

    if not items:
        return []

    cnpj_fundo_norm = _normalize_cnpj_any(cnpj_fundo)
    ingested_at = datetime.now(UTC)
    rows: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        id_op = str(item.get("idOperacaoRecebivel", ""))
        source_id = f"{cnpj_fundo_norm}|{id_op}|rem"

        dt = parse_iso_or_none(item.get("data"))

        rows.append(
            {
                "tenant_id": tenant_id,
                "data_importacao": dt.date() if dt else None,
                # Fundo
                "fundo_doc": _normalize_cnpj_any(item.get("cnpjFundo")) or cnpj_fundo_norm,
                "fundo_nome": str(item.get("nomeFundo", "")),
                # Gestor
                "gestor_doc": _normalize_cnpj_any(item.get("cnpjGestor")),
                "gestor_nome": str(item.get("gestor", "")),
                # Cedente
                "cedente_doc": _normalize_cnpj_any(item.get("documentoCedente")),
                "cedente_nome": str(item.get("nomeCedente", "")),
                # Operacao
                "id_operacao_recebivel": id_op,
                "nome_arquivo": str(item.get("nomeArquivo", "")),
                "nome_arquivo_entrada": str(item.get("nomeArquivoEntrada", "")),
                "tipo_recebivel": str(item.get("tipoRecebivel", "")),
                # Fatos
                "remessa": to_decimal(item.get("remessa")),
                "reembolso": to_decimal(item.get("reembolso")),
                "recompra": to_decimal(item.get("recompra")),
                "valor_total": to_decimal(item.get("valorTotal")),
                # Flag
                "coobrigacao": _parse_bool_sim_nao(item.get("coobrigacao")),
                # Proveniencia
                **build_provenance(
                    source_id=source_id,
                    item=item,
                    ingested_at=ingested_at,
                    source_updated_at=dt,
                ),
            }
        )

    return rows
