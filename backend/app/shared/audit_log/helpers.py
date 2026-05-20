"""Helpers compartilhados pra audit (decision_log).

Promovido em Fase 1.5 do refactor "espelho fiel" (2026-05-20). Antes, o
`_log_silver_replacement` vivia inline em `qitech/etl.py` -- mover pra ca
permite que outros adapters (Bitfin, futuros) usem o mesmo padrao de audit
quando implementarem replace-by-partition.

Funcoes:
  - `log_silver_replacement`: grava 1 entry `DATA_CORRECTION` no
    `decision_log` com snapshot das orfas removidas + business keys + JSON
    serializavel.
  - `json_safe`: converte Decimal/UUID/date/datetime pra str (compat
    JSONB).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.audit_log.decision_log import DecisionLog, DecisionType


def json_safe(value: Any) -> Any:
    """Converte tipos nao-JSON pra string (Decimal/UUID/date/datetime).

    Pra usar diretamente em campos JSONB do decision_log. Tipos primitivos
    (bool/int/float/str/None) passam intactos.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (UUID, datetime, date)):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    return str(value)


def json_safe_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Aplica `json_safe` a cada value de um dict."""
    return {k: json_safe(v) for k, v in d.items()}


async def log_silver_replacement(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    adapter_name: str,
    adapter_version: str,
    endpoint_name: str,
    table_name: str,
    raw_id: UUID,
    data_referencia: date,
    unidade_administrativa_id: UUID | None,
    orphan_rows: list[dict[str, Any]],
    conflict_columns: list[str],
    triggered_by: str,
    reason: str,
) -> None:
    """Grava 1 entry `DATA_CORRECTION` no `decision_log` com snapshot das orfas.

    Trilha de auditoria do que sumiu do warehouse via replace-by-partition.
    Reusa o schema do `decision_log` (CLAUDE.md secao 14). Snapshot e os
    business keys das orfas vao em:

      output.business_keys              -> list[dict[col, value]]
      output.snapshot_critical_fields   -> list[dict[col, JSON-safe value]]

    Adapter-agnostic: chamado por qualquer adapter que implemente
    replace-by-partition. O QiTech foi o primeiro (Fase 1.3).

    Nao faz commit -- caller decide. Grava na mesma transacao do
    DELETE pra atomicidade.
    """
    serializable_orphans = [json_safe_dict(row) for row in orphan_rows]
    business_keys = [
        {c: snap.get(c) for c in conflict_columns} for snap in serializable_orphans
    ]
    entry = DecisionLog(
        tenant_id=tenant_id,
        decision_type=DecisionType.DATA_CORRECTION,
        endpoint_name=endpoint_name,
        rule_or_model=adapter_name,
        rule_or_model_version=adapter_version,
        inputs_ref={
            "raw_id": str(raw_id),
            "table_name": table_name,
            "data_referencia": data_referencia.isoformat(),
            "ua_id": str(unidade_administrativa_id)
            if unidade_administrativa_id
            else None,
        },
        output={
            "reason": reason,
            "removed_count": len(orphan_rows),
            "business_keys": business_keys,
            "snapshot_critical_fields": serializable_orphans,
        },
        explanation=(
            f"Replace-by-partition removeu {len(orphan_rows)} row(s) orfa(s) "
            f"do silver {table_name} (raw_id={raw_id}). Estes registros "
            f"existiam no warehouse mas sumiram do payload em re-sync "
            f"— provavel correcao retroativa pela fonte."
        ),
        triggered_by=triggered_by,
    )
    db.add(entry)
