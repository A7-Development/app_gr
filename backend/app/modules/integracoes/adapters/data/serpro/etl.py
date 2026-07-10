"""ETL SERPRO NF-e -- consulta + persistencia no bronze wh_serpro_raw_nfe.

Fluxo de `consultar_e_persistir`:

    GET /v1/nfe/{chave} (cobrado pelo SERPRO quando 200)
    -> sha256 do body EXATO
    -> INSERT bronze com CAST(text AS jsonb) — dedup por
       (tenant, chave, sha256): payload identico ao ja persistido nao
       duplica linha (estado nao mudou)
    -> decision_log (SYNC) com cstat/qtd_eventos/changed — toda chamada
       paga fica auditavel, inclusive as que nao mudaram nada

Commit e responsabilidade do CALLER (o ETL apenas flusha) — permite compor
N consultas numa transacao ou usar em endpoint com get_db.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.data.serpro.client import (
    SerproClient,
    SerproNfeResponse,
)
from app.modules.integracoes.adapters.data.serpro.version import ADAPTER_VERSION
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.warehouse.serpro_raw_nfe import SerproRawNfe

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SerproIngestResult:
    """Desfecho de uma consulta persistida."""

    raw_id: UUID
    chave: str
    cstat: int | None
    qtd_eventos: int
    # True quando o payload e um snapshot INEDITO (estado mudou desde a
    # ultima consulta); False quando o dedup casou com linha existente.
    changed: bool
    response: SerproNfeResponse


async def persistir_snapshot(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    response: SerproNfeResponse,
    trigger: str,
) -> SerproIngestResult:
    """Grava um snapshot ja consultado no bronze (dedup por sha256).

    Separado de `consultar_e_persistir` para reuso na bancada (payload ja
    em maos) e nos testes.
    """
    sha = hashlib.sha256(response.text.encode("utf-8")).hexdigest()
    cstat = response.cstat
    qtd_eventos = len(response.eventos)

    stmt = (
        pg_insert(SerproRawNfe)
        .values(
            tenant_id=tenant_id,
            chave_acesso=response.chave,
            # CAST(text AS jsonb) preserva a precisao numerica do gateway
            # (numeros grandes podem vir em notacao cientifica; jsonb
            # guarda numeric arbitrario, float do Python nao).
            payload=sa.cast(sa.literal(response.text), JSONB),
            cstat=cstat,
            qtd_eventos=qtd_eventos,
            trigger=trigger,
            request_tag=response.request_tag,
            payload_sha256=sha,
            fetched_by_version=ADAPTER_VERSION,
        )
        .on_conflict_do_nothing(constraint="uq_wh_serpro_raw_nfe_dedup")
        .returning(SerproRawNfe.id)
    )
    inserted_id = (await db.execute(stmt)).scalar_one_or_none()
    changed = inserted_id is not None

    if not changed:
        existing = await db.execute(
            sa.select(SerproRawNfe.id).where(
                SerproRawNfe.tenant_id == tenant_id,
                SerproRawNfe.chave_acesso == response.chave,
                SerproRawNfe.payload_sha256 == sha,
            )
        )
        inserted_id = existing.scalar_one()

    db.add(
        DecisionLog(
            tenant_id=tenant_id,
            decision_type=DecisionType.SYNC,
            rule_or_model="serpro_adapter",
            rule_or_model_version=ADAPTER_VERSION,
            inputs_ref={
                "chave": response.chave,
                "trigger": trigger,
                "request_tag": response.request_tag,
            },
            output={
                "raw_id": str(inserted_id),
                "cstat": cstat,
                "qtd_eventos": qtd_eventos,
                "changed": changed,
                "latency_ms": response.latency_ms,
            },
            explanation=(
                "Consulta SERPRO NF-e persistida no bronze"
                if changed
                else "Consulta SERPRO NF-e sem mudanca de estado (dedup)"
            ),
            triggered_by=f"serpro:{trigger}",
        )
    )
    await db.flush()

    logger.info(
        "serpro nfe chave=%s cstat=%s eventos=%d changed=%s trigger=%s",
        response.chave,
        cstat,
        qtd_eventos,
        changed,
        trigger,
    )
    return SerproIngestResult(
        raw_id=inserted_id,
        chave=response.chave,
        cstat=cstat,
        qtd_eventos=qtd_eventos,
        changed=changed,
        response=response,
    )


async def consultar_e_persistir(
    db: AsyncSession,
    client: SerproClient,
    *,
    tenant_id: UUID,
    chave: str,
    trigger: str,
    request_tag: str | None = None,
) -> SerproIngestResult:
    """Consulta a chave no SERPRO (chamada COBRADA) e persiste o snapshot.

    Erros do client (SerproNotFoundError, SerproThrottledError, ...) sobem
    para o caller decidir (backoff, marcar monitoracao, etc). Commit e do
    caller.
    """
    response = await client.consulta_nfe(chave, request_tag=request_tag)
    return await persistir_snapshot(
        db, tenant_id=tenant_id, response=response, trigger=trigger
    )
