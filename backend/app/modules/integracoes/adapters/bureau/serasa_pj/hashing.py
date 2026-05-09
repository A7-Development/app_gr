"""Deterministic row hashing — `hash_origem` em proveniencia silver.

Replica padrao dos outros adapters (Bitfin, QiTech) em vez de extrair
para shared kernel: mantem cada adapter independente e sem acoplamento.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _default(obj: Any) -> Any:
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.hex()
    raise TypeError(f"Type {type(obj)} is not JSON serializable")


def sha256_of_row(row: dict[str, Any] | list[Any]) -> str:
    """SHA256 estavel do payload de uma row (usado em `hash_origem`)."""
    payload = json.dumps(
        row, default=_default, sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_of_payload(payload: bytes | str) -> str:
    """SHA256 do payload bruto (usado em `wh_serasa_pj_raw_relatorio.payload_sha256`).

    Caller passa o body cru da resposta HTTP — bytes preferencialmente,
    mas string serializada tambem funciona.
    """
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
