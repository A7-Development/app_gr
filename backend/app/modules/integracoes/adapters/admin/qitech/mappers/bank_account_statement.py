"""Mapper: payload /v2/bank-account/statement/{ag}/{cc}/{ini}/{fim} -> dicts canonicos.

Granularidade: 1 chamada -> N linhas em wh_extrato_bancario (1 por lancamento).

source_id por lancamento = `bank_account_statement|{ua}|{ag}|{conta}|{YYYY-MM-DD}|{sha16(item)}`.
sha16 protege contra QiTech nao expor id estavel; mesmo lancamento re-fetched
nao duplica via UQ (tenant, source_id).

Schema esperado [INFERIDO ate vermos payload real]:

    [  // ou {"lancamentos": [...]} ou {"items": [...]}
        {
            "data": "2026-01-15",                   # ou "dataLancamento", "dataMovimento"
            "valor": 1234.56,                       # ou "valorMovimento"
            "tipo": "C",                            # ou "tipoOperacao", "natureza"
            "historico": "TED ...",                 # ou "descricao"
            "documento": "12345",                   # opcional
            "contrapartida": {                      # opcional, varios formatos
                "nome": "Fornecedor X",
                "cnpj": "99999999000199"
            },
            ...
        },
        ...
    ]

Mapper aceita payload sendo: lista direta, dict com chave "lancamentos",
ou dict com chave "items". Lancamentos sem `data` ou sem `valor` sao
descartados (campos critical) — caller pode contar `len(returned)` vs
`len(items_brutos)` pra estimar perda.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.admin.qitech.hashing import sha256_of_row
from app.modules.integracoes.adapters.admin.qitech.mappers._common import (
    build_provenance,
    normalize_str_or_none,
    parse_iso_or_none,
    to_decimal,
)


def _extract_items(payload: Any) -> list[Any]:
    """Encontra a lista de lancamentos no payload, tolerando varios formatos."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("lancamentos", "lançamentos", "items", "extrato", "movimentos"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
        # Forma 4: nested em "relatorios"/"relatórios"
        relatorios = payload.get("relatorios") or payload.get("relatórios")
        if isinstance(relatorios, dict):
            for key in ("statement", "extrato", "lancamentos", "lançamentos"):
                v = relatorios.get(key)
                if isinstance(v, list):
                    return v
    return []


def _pick_data_lancamento(item: dict[str, Any]) -> date | None:
    for key in (
        "dataLancamento",
        "dataLançamento",
        "data",
        "dataLiquidacao",
        "dataLiquidação",
    ):
        v = item.get(key)
        if isinstance(v, str) and v:
            parsed = parse_iso_or_none(v)
            if parsed:
                return parsed.date()
            # Tenta YYYY-MM-DD puro
            try:
                return date.fromisoformat(v[:10])
            except ValueError:
                continue
    return None


def _pick_data_movimento(item: dict[str, Any]) -> date | None:
    for key in ("dataMovimento", "dataMovimentacao", "dataOperacao"):
        v = item.get(key)
        if isinstance(v, str) and v:
            parsed = parse_iso_or_none(v)
            if parsed:
                return parsed.date()
            try:
                return date.fromisoformat(v[:10])
            except ValueError:
                continue
    return None


def _pick_valor(item: dict[str, Any]) -> Decimal | None:
    for key in ("valor", "valorMovimento", "valorMovimentacao", "amount"):
        if key in item and item[key] is not None:
            try:
                return to_decimal(item[key])
            except Exception:  # noqa: BLE001
                continue
    return None


def _pick_tipo(item: dict[str, Any]) -> str | None:
    """Normaliza tipo para 'D' (debito/saida) ou 'C' (credito/entrada)."""
    for key in ("tipo", "tipoOperacao", "tipoDeOperacao", "natureza"):
        v = item.get(key)
        if v is None:
            continue
        s = str(v).strip().upper()
        if not s:
            continue
        if s.startswith("D") or s in ("DEBIT", "DEBITO", "DÉBITO", "SAIDA", "SAÍDA", "-"):
            return "D"
        if s.startswith("C") or s in ("CREDIT", "CREDITO", "CRÉDITO", "ENTRADA", "+"):
            return "C"
    # Fallback: se valor explicitamente negativo, e debito.
    valor = _pick_valor(item)
    if valor is not None and valor < 0:
        return "D"
    if valor is not None and valor > 0:
        return "C"
    return None


def _pick_contrapartida(item: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extrai (nome, doc) da contraparte se presente."""
    cp = item.get("contrapartida") or item.get("contraparte")
    if isinstance(cp, dict):
        nome = normalize_str_or_none(cp.get("nome") or cp.get("name"))
        doc = normalize_str_or_none(
            cp.get("cnpj") or cp.get("cpf") or cp.get("documento") or cp.get("doc")
        )
        return nome, doc
    return None, None


def map_bank_account_statement(
    *,
    payload: Any,
    tenant_id: UUID,
    unidade_administrativa_id: UUID,
    agencia: str,
    conta: str,
) -> list[dict[str, Any]]:
    """Mapeia payload de extrato em N linhas canonicas.

    Lancamentos sem (data_lancamento E valor E tipo) sao descartados — sao
    campos criticos. Caller decide se loga warning sobre `len(input)
    -> len(output)`.
    """
    items = _extract_items(payload)
    if not items:
        return []

    ingested_at = datetime.now(UTC)
    rows: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        data_lanc = _pick_data_lancamento(item)
        valor = _pick_valor(item)
        tipo = _pick_tipo(item)

        if data_lanc is None or valor is None or tipo is None:
            continue

        # Valor sempre absoluto no warehouse — sinal vai em `tipo`.
        valor_abs = abs(valor)

        contraparte_nome, contraparte_doc = _pick_contrapartida(item)

        item_hash = sha256_of_row(item)
        source_id = (
            f"bank_account_statement|{unidade_administrativa_id}|"
            f"{agencia}|{conta}|{data_lanc.isoformat()}|{item_hash[:16]}"
        )

        # Banco no envelope (nem sempre presente em cada item)
        banco = item.get("banco") if isinstance(item.get("banco"), dict) else {}
        banco_codigo = normalize_str_or_none(
            banco.get("codigo") or banco.get("código") or banco.get("code")
        )
        banco_nome = normalize_str_or_none(banco.get("nome") or banco.get("name"))

        moeda = normalize_str_or_none(item.get("moeda")) or "BRL"
        src_updated = parse_iso_or_none(
            item.get("dataAtualizacao") or item.get("updatedAt")
        )

        rows.append(
            {
                "tenant_id": tenant_id,
                "unidade_administrativa_id": unidade_administrativa_id,
                "agencia": agencia,
                "conta": conta,
                "banco_codigo": banco_codigo,
                "banco_nome": banco_nome,
                "moeda": moeda,
                "data_lancamento": data_lanc,
                "data_movimento": _pick_data_movimento(item),
                "valor": valor_abs,
                "tipo": tipo,
                "historico": normalize_str_or_none(
                    item.get("historico") or item.get("histórico")
                ),
                "descricao": normalize_str_or_none(
                    item.get("descricao") or item.get("descrição")
                ),
                "documento": normalize_str_or_none(
                    item.get("documento") or item.get("nrDocumento")
                ),
                "contrapartida_nome": contraparte_nome,
                "contrapartida_doc": contraparte_doc,
                **build_provenance(
                    source_id=source_id,
                    item=item,
                    ingested_at=ingested_at,
                    source_updated_at=src_updated,
                ),
            }
        )

    return rows
