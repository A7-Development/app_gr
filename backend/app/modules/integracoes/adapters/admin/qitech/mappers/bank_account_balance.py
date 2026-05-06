"""Mapper: payload /v2/bank-account/balance/{ag}/{cc}/{data} -> dict canonico.

Granularidade: 1 chamada -> 1 linha em wh_saldo_bancario_diario (PK
(tenant, ua, agencia, conta, data_posicao) garantido pela UQ via
source_id).

source_id = `bank_account_balance|{ua_id}|{agencia}|{conta}|{YYYY-MM-DD}`.

Schema esperado [INFERIDO ate vermos payload real]:

    {
        "saldo": 12345.67,                # ou "valor", "valorTotal", "saldoTotal"
        "moeda": "BRL",                   # opcional
        "banco": { "codigo": "237", "nome": "Bradesco" },  # opcional
        "dataDaPosicao": "2026-01-15T...",                 # opcional, redundante com path
        ...
    }

O mapper tenta multiplas chaves comuns pra ser tolerante. Quando vermos o
payload de verdade, removemos as alternativas que nao aparecem.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.admin.qitech.mappers._common import (
    build_provenance,
    normalize_str_or_none,
    parse_iso_or_none,
    to_decimal,
)


def _pick_saldo(payload: dict[str, Any]) -> Decimal | None:
    """Tenta extrair o saldo de chaves comuns. Retorna None se nenhuma existir."""
    for key in ("saldo", "valor", "valorTotal", "saldoTotal", "balance"):
        if key in payload and payload[key] is not None:
            try:
                return to_decimal(payload[key])
            except Exception:
                continue
    return None


def _pick_banco(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extrai (codigo, nome) do banco se presente. Aceita formatos comuns."""
    # Forma 1: {"banco": {"codigo": "237", "nome": "Bradesco"}}
    banco = payload.get("banco")
    if isinstance(banco, dict):
        codigo = normalize_str_or_none(
            banco.get("codigo") or banco.get("código") or banco.get("code")
        )
        nome = normalize_str_or_none(
            banco.get("nome") or banco.get("name")
        )
        return codigo, nome
    # Forma 2: chaves planas no root
    codigo = normalize_str_or_none(
        payload.get("codigoBanco") or payload.get("códigoBanco")
    )
    nome = normalize_str_or_none(
        payload.get("nomeBanco") or payload.get("instituicao")
    )
    return codigo, nome


def map_bank_account_balance(
    *,
    payload: Any,
    tenant_id: UUID,
    unidade_administrativa_id: UUID,
    agencia: str,
    conta: str,
    data_posicao: date,
) -> list[dict[str, Any]]:
    """Mapeia payload de saldo em 0 ou 1 linha canonica.

    Retorna lista vazia se:
    - payload nao for dict
    - nenhuma chave de saldo conhecida estiver presente

    Caller (ETL) decide se logar warning ou simplesmente ignorar.
    """
    if not isinstance(payload, dict):
        return []

    saldo = _pick_saldo(payload)
    if saldo is None:
        return []

    banco_codigo, banco_nome = _pick_banco(payload)
    moeda = normalize_str_or_none(payload.get("moeda")) or "BRL"

    # source_updated_at: se payload trouxer data interna, usa; senao deixa None.
    src_updated = parse_iso_or_none(
        payload.get("dataDaPosicao") or payload.get("dataDaPosição")
    )

    source_id = (
        f"bank_account_balance|{unidade_administrativa_id}|"
        f"{agencia}|{conta}|{data_posicao.isoformat()}"
    )

    return [
        {
            "tenant_id": tenant_id,
            "unidade_administrativa_id": unidade_administrativa_id,
            "data_posicao": data_posicao,
            "agencia": agencia,
            "conta": conta,
            "banco_codigo": banco_codigo,
            "banco_nome": banco_nome,
            "moeda": moeda,
            "saldo": saldo,
            **build_provenance(
                source_id=source_id,
                item=payload,
                ingested_at=datetime.now(UTC),
                source_updated_at=src_updated,
            ),
        }
    ]
