"""Deterministic row hashing para deteccao de mudanca (proveniencia).

Copia do padrao ja estabelecido no adapter Bitfin (ver CLAUDE.md §11 —
"Reusar ... sha256_of_row ... extrair para _qitech_common/ se util, ou
deixar no Bitfin e replicar padrao"). Optado por replicar: mantem cada
adapter independente e sem acoplamento cruzado.
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


def sha256_of_row(row: dict[str, Any]) -> str:
    """SHA256 estavel do payload de uma row (usado em `hash_origem`)."""
    payload = json.dumps(row, default=_default, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
