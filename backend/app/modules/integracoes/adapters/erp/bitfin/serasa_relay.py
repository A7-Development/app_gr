"""Relay: replica consultas Serasa (Relato PJ) do Bitfin para wh_serasa_pj_*.

Le `dbo.ConsultaFinanceira` (gzip JSON) incrementalmente por
`ConsultaFinanceiraId`, descomprime o laudo, roda o mapper Serasa existente
(`map_pj_analitico`) e grava no mesmo silver `wh_serasa_pj_*`. NAO faz chamada
paga a Serasa — so replica o que ja foi consultado dentro do Bitfin.

- **Watermark** = `MAX(bitfin_consulta_id)` por tenant em `wh_serasa_pj_raw_relatorio`.
- **Idempotente** via indice unico parcial `(tenant_id, bitfin_consulta_id)` +
  `ON CONFLICT DO NOTHING`.
- **Self-healing parcial**: raw + silver na MESMA transacao por linha; falha →
  rollback (linha nao entra no watermark) → reprocessa num run futuro. O cursor
  local avanca mesmo em falha pra nao travar o run (a falha vai em `errors` →
  decision_log → UI). Falha NO MEIO com linhas posteriores OK fica como gap
  (visivel em errors) — reprocesso manual por id se necessario.

Endpoint: `bitfin.serasa_relay` (ver `endpoint_catalog.py`). Disparado pelo
dispatcher como qualquer sync de endpoint (`adapter_sync_endpoint`).
"""

from __future__ import annotations

import asyncio
import gzip
import json
from datetime import UTC
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.integracoes.adapters.bureau.serasa_pj.hashing import (
    sha256_of_row,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.mappers.pj_analitico import (
    map_pj_analitico,
)
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.modules.integracoes.adapters.erp.bitfin.connection import fetch_rows
from app.modules.integracoes.adapters.erp.bitfin.queries import bitfin as q
from app.modules.integracoes.services.serasa_pj_query import (
    persist_serasa_pj_silver,
)
from app.warehouse.serasa_pj_raw_relatorio import SerasaPjRawRelatorio

_REPORT = "RELATORIO_AVANCADO_PJ_ANALITICO"
_RELAY_VERSION = "bitfin_serasa_relay_v1"
_BATCH_SIZE = 100
# Teto de seguranca por run. O backfill (~2.4k) drena de uma vez; em regime
# incremental cada run pega so as novas (poucas).
_MAX_ROWS_PER_RUN = 10_000


def _extract_cnpj(payload: dict[str, Any]) -> str:
    """CNPJ cheio (14 dig) de identificationReport.documentNumber do laudo.

    O `Documento` da ConsultaFinanceira e so a raiz (9 dig); o CNPJ completo
    mora dentro do JSON.
    """
    try:
        doc = payload["reports"][0]["identificationReport"]["documentNumber"]
    except (KeyError, IndexError, TypeError):
        doc = ""
    return "".join(c for c in str(doc) if c.isdigit())[:14]


async def _watermark(tenant_id: UUID) -> int:
    async with AsyncSessionLocal() as db:
        v = (
            await db.execute(
                text(
                    "SELECT COALESCE(MAX(bitfin_consulta_id), 0) "
                    "FROM wh_serasa_pj_raw_relatorio "
                    "WHERE tenant_id = :t AND bitfin_consulta_id IS NOT NULL"
                ),
                {"t": tenant_id},
            )
        ).scalar_one()
    return int(v or 0)


async def _process_one(tenant_id: UUID, row: dict[str, Any]) -> str:
    """Ingere uma ConsultaFinanceira (raw + silver, 1 tx). 'ok' | 'skip'."""
    cid = int(row["ConsultaFinanceiraId"])
    blob = row.get("Relatorio")
    if blob is None:
        return "skip"
    payload = json.loads(gzip.decompress(bytes(blob)).decode("utf-8"))
    cnpj = _extract_cnpj(payload)
    data_final = row.get("DataFinal")
    consulted_at = (
        data_final.replace(tzinfo=UTC)
        if (data_final is not None and data_final.tzinfo is None)
        else data_final
    )

    raw_id = uuid4()
    async with AsyncSessionLocal() as db:
        ins = (
            pg_insert(SerasaPjRawRelatorio.__table__)
            .values(
                id=raw_id,
                tenant_id=tenant_id,
                cnpj=cnpj,
                requested_report=_REPORT,
                actual_report_returned=_REPORT,
                environment=Environment.PRODUCTION,
                status_code=200,
                cost_center=None,
                triggered_by=f"bitfin:consulta:{cid}",
                payload=payload,
                payload_sha256=sha256_of_row(payload),
                latency_ms=None,
                fetched_at=consulted_at,
                fetched_by_version=_RELAY_VERSION,
                bitfin_consulta_id=cid,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "bitfin_consulta_id"],
                index_where=text("bitfin_consulta_id IS NOT NULL"),
            )
            .returning(SerasaPjRawRelatorio.__table__.c.id)
        )
        inserted = (await db.execute(ins)).scalar_one_or_none()
        if inserted is None:
            return "skip"  # ja ingerido (idempotencia)
        mapped = map_pj_analitico(
            payload=payload,
            tenant_id=tenant_id,
            raw_id=raw_id,
            cnpj=cnpj,
            consulted_at=consulted_at,
            requested_report=_REPORT,
            actual_report_returned=_REPORT,
        )
        await persist_serasa_pj_silver(db, mapped)
        await db.commit()
    return "ok"


async def relay_serasa_pj(
    tenant_id: UUID,
    config: BitfinConfig,
    *,
    triggered_by: str = "system:scheduler",
    batch_size: int = _BATCH_SIZE,
    max_rows: int = _MAX_ROWS_PER_RUN,
) -> dict[str, Any]:
    """Replica consultas Serasa novas do Bitfin (Id > watermark) pro silver."""
    _ = triggered_by
    summary: dict[str, Any] = {
        "ok": True,
        "ingested": 0,
        "skipped": 0,
        "errors": [],
    }
    cursor = await _watermark(tenant_id)
    while summary["ingested"] + summary["skipped"] < max_rows:
        rows = await asyncio.to_thread(
            fetch_rows,
            config,
            config.database_bitfin,
            q.SELECT_CONSULTA_FINANCEIRA_SINCE_ID,
            (batch_size, cursor),
        )
        if not rows:
            break
        for r in rows:
            cid = int(r["ConsultaFinanceiraId"])
            try:
                outcome = await _process_one(tenant_id, r)
                summary["ingested" if outcome == "ok" else "skipped"] += 1
            except Exception as e:
                summary["errors"].append(f"id={cid}: {type(e).__name__}: {e}")
            cursor = cid  # avanca sempre (rows ordenadas asc) → sem loop infinito

    summary["watermark"] = cursor
    if summary["errors"]:
        summary["ok"] = False
    return summary
