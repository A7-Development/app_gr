"""Backfill service: create/get/process backfill jobs.

3 funcoes publicas:
- `create_backfill_job(...)` — chamada pelo router POST /backfill
- `get_backfill_job(job_id)` — chamada pelo router GET /backfill/{id}
- `process_next_pending_job()` — chamada pelo APScheduler tick a cada 5s.
  Pega 1 job `pending`, marca `running`, processa as datas em serie,
  atualiza arrays e status final.

`process_next_pending_job` usa SELECT ... FOR UPDATE SKIP LOCKED pra evitar
que 2 workers (eventualmente em workers paralelos) peguem o mesmo job. No
deploy atual (gr-api --workers 1) o lock e teorico, mas e barato.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.models.backfill_job import BackfillJob
from app.modules.integracoes.services.sync_runner import run_sync_endpoint

logger = logging.getLogger("gr.integracoes.backfill")

# Pause sustentada entre datas dentro do MESMO job. Necessario porque o
# APScheduler `INTERVAL_SECONDS` so controla a frequencia de busca por novos
# jobs, nao a velocidade interna do `_process_job_dates`. Sem esse sleep,
# `run_sync_endpoint` e chamado em loop tao rapido quanto a latencia do
# vendor permite (~5 req/s pra QiTech) -- e o WAF Imperva da Singulare
# bloqueia rajadas, devolvendo 403 sistematico a partir de ~60 requests/min
# per-IP. Validado em 2026-05-15: 2 batches de ~1030 datas resultaram em 54
# sucessos + 975 falhas cada (mesmo padrao).
#
# Default 2s = 0.5 req/s sustained, bem abaixo do limite WAF. Configuravel
# por env var pra acelerar (1s) quando precisar OU desacelerar (4s+) se o
# WAF ainda reagir.
_INTER_DATE_SLEEP_S: float = float(
    os.environ.get("GR_BACKFILL_INTER_DATE_SLEEP_S", "2.0")
)


async def create_backfill_job(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment,
    unidade_administrativa_id: UUID | None,
    endpoint_name: str,
    dates: list[date],
    created_by: str,
) -> BackfillJob:
    """Insere job pending com lista de datas. Worker pega no proximo tick."""
    if not dates:
        raise ValueError("dates must contain at least 1 date")
    # Dedupe + ordena (ajuda no debug visual da UI)
    dates_sorted = sorted(set(dates))
    job = BackfillJob(
        tenant_id=tenant_id,
        source_type=source_type.value,
        environment=environment.value,
        unidade_administrativa_id=unidade_administrativa_id,
        endpoint_name=endpoint_name,
        dates_pending=dates_sorted,
        dates_done=[],
        dates_failed=[],
        status="pending",
        created_by=created_by,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_backfill_job(
    db: AsyncSession, *, tenant_id: UUID, job_id: UUID
) -> BackfillJob | None:
    """Lookup escopado por tenant — defensivo, mesmo o FK ja garantindo."""
    stmt = select(BackfillJob).where(
        BackfillJob.id == job_id,
        BackfillJob.tenant_id == tenant_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_active_backfill_jobs(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    endpoint_name: str | None = None,
) -> list[BackfillJob]:
    """Lista jobs ativos (pending/running) — usado pela UI pra mostrar
    progresso quando recarrega a pagina no meio de um backfill."""
    stmt = (
        select(BackfillJob)
        .where(
            BackfillJob.tenant_id == tenant_id,
            BackfillJob.source_type == source_type.value,
            BackfillJob.status.in_(["pending", "running"]),
        )
        .order_by(BackfillJob.created_at.desc())
    )
    if endpoint_name is not None:
        stmt = stmt.where(BackfillJob.endpoint_name == endpoint_name)
    return list((await db.execute(stmt)).scalars().all())


async def cancel_backfill_job(
    db: AsyncSession, *, tenant_id: UUID, job_id: UUID
) -> BackfillJob | None:
    """Marca job como cancelled. Worker respeita a flag no proximo loop
    de data — datas ja processadas ficam em done/failed, o resto fica
    em pending pra registro."""
    job = await get_backfill_job(db, tenant_id=tenant_id, job_id=job_id)
    if job is None:
        return None
    if job.status in ("done", "failed", "cancelled"):
        return job  # idempotente
    job.status = "cancelled"
    job.updated_at = datetime.now(UTC)
    job.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(job)
    return job


async def process_next_pending_job() -> dict[str, Any]:
    """Worker tick: pega 1 job pending, processa serialmente as datas.

    Estrategia anti-corrida: SELECT ... FOR UPDATE SKIP LOCKED na tabela
    + UPDATE imediato pra `running` na mesma transacao. Workers concorrentes
    nunca pegam o mesmo job. Em deploys com --workers 1 o lock e teorico.

    Apos pegar o job, processa cada data em serie chamando `run_sync_endpoint`
    com `since=date`. Cada data sucesso/falha individual eh registrada nos
    arrays. Falha critica (config invalida, etc) marca job como `failed`
    e para.
    """
    summary: dict[str, Any] = {
        "picked_job_id": None,
        "dates_processed": 0,
        "dates_succeeded": 0,
        "dates_failed": 0,
        "elapsed_seconds": 0.0,
    }
    started_at = datetime.now(UTC)

    # 1. Pega 1 job pending com lock atomico
    async with AsyncSessionLocal() as db:
        stmt = (
            select(BackfillJob)
            .where(BackfillJob.status == "pending")
            .order_by(BackfillJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = (await db.execute(stmt)).scalar_one_or_none()
        if job is None:
            return summary

        job_id = job.id
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.updated_at = datetime.now(UTC)
        await db.commit()

    summary["picked_job_id"] = str(job_id)
    logger.info("backfill: picked job %s, %d dates pending", job_id, len(job.dates_pending))

    # 2. Processa serialmente. Re-le o job a cada N pra captar cancelamento.
    try:
        await _process_job_dates(job_id, summary)
    except Exception as e:
        logger.exception("backfill: job %s falhou criticamente: %s", job_id, e)
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(BackfillJob)
                .where(BackfillJob.id == job_id)
                .values(
                    status="failed",
                    completed_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            await db.commit()

    summary["elapsed_seconds"] = round(
        (datetime.now(UTC) - started_at).total_seconds(), 2
    )
    return summary


# Re-le o job a cada N datas pra detectar cancelamento sem segurar a row.
_CANCEL_CHECK_EVERY_N = 5


async def _process_job_dates(job_id: UUID, summary: dict[str, Any]) -> None:
    """Loop principal — processa as datas em serie, persiste progresso
    apos cada uma. Re-le o job a cada _CANCEL_CHECK_EVERY_N datas pra
    abortar se operador cancelou."""
    while True:
        # 1 transacao por iteracao — captura estado atual + processa 1 data
        async with AsyncSessionLocal() as db:
            job = await db.get(BackfillJob, job_id)
            if job is None or job.status != "running":
                return  # Cancelado ou desapareceu
            if not job.dates_pending:
                # Acabou
                job.status = "done"
                job.completed_at = datetime.now(UTC)
                job.updated_at = datetime.now(UTC)
                await db.commit()
                return

            current_date = job.dates_pending[0]
            tenant_id = job.tenant_id
            source_type = SourceType(job.source_type)
            environment = Environment(job.environment)
            endpoint_name = job.endpoint_name
            ua_id = job.unidade_administrativa_id

        # Chamada externa fora da transacao do DB (libera a conexao do pool)
        success = True
        error_message: str | None = None
        try:
            result = await run_sync_endpoint(
                tenant_id,
                source_type,
                endpoint_name,
                environment=environment,
                since=current_date,
                triggered_by=f"backfill:{job_id}",
                unidade_administrativa_id=ua_id,
            )
            if not result.get("ok"):
                success = False
                error_message = "; ".join(result.get("errors") or []) or "sync nao-ok"
        except Exception as e:
            success = False
            error_message = f"{type(e).__name__}: {e}"
            logger.exception(
                "backfill: data %s do job %s falhou: %s",
                current_date,
                job_id,
                error_message,
            )

        # Persiste o resultado da data
        async with AsyncSessionLocal() as db:
            job = await db.get(BackfillJob, job_id)
            if job is None:
                return
            if job.status != "running":
                return  # Cancelado entre transacoes
            # Move current_date de pending pra done ou failed
            new_pending = [d for d in job.dates_pending if d != current_date]
            if success:
                new_done = list(job.dates_done) + [current_date]
                new_failed = job.dates_failed
                summary["dates_succeeded"] += 1
            else:
                new_done = job.dates_done
                new_failed = list(job.dates_failed) + [
                    {"date": current_date.isoformat(), "error": error_message}
                ]
                summary["dates_failed"] += 1
            job.dates_pending = new_pending
            job.dates_done = new_done
            job.dates_failed = new_failed
            job.updated_at = datetime.now(UTC)
            if not new_pending:
                job.status = "done"
                job.completed_at = datetime.now(UTC)
            await db.commit()

        summary["dates_processed"] += 1
        if not new_pending:
            return

        # Rate limit cooperativo com WAF Imperva (Singulare/QiTech). Ver
        # comentario no topo do modulo. Acontece APOS commit do progresso
        # da data atual, antes de ir pra proxima -- se o operador cancelar
        # durante esse sleep, a proxima iteracao captura via SELECT em
        # _process_job_dates.
        if _INTER_DATE_SLEEP_S > 0:
            await asyncio.sleep(_INTER_DATE_SLEEP_S)
