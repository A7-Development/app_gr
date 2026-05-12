"""JSON serializer used by SQLAlchemy for JSONB column encoding.

Stdlib json.dumps cannot serialize date / datetime / Decimal / UUID / bytes,
which are all common in bronze-layer payloads coming from external adapters
(pyodbc returns date for SQL DATE columns, Decimal for NUMERIC, etc.). Wired
into the async engine via `json_serializer=` so any Mapped[...] = JSONB column
accepts these natively.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def default(obj: Any) -> Any:
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.hex()
    raise TypeError(f"Type {type(obj)} is not JSON serializable")


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=default, ensure_ascii=False)
