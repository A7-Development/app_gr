"""APScheduler setup — integrado ao lifespan do FastAPI."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.scheduler import sync_dispatcher
from app.scheduler.jobs import backfill_worker, qitech_jobs_poll, reconciler

logger = logging.getLogger("gr.scheduler")

_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler:
    """Instancia e inicia o scheduler; chamado no lifespan do app.

    Jobs:
      - sync_dispatcher (1 min): le `tenant_source_config.sync_frequency_minutes`
        e dispara `run_sync_one` por linha quando passou o intervalo. Substitui
        o antigo bitfin_sync hardcoded — agora cadencia e config por tenant.
      - qitech_jobs_poll (5 min): observabilidade do fluxo assincrono QiTech
        (callback perdido, jobs orfaos). Ortogonal ao dispatcher.
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
    _scheduler.add_job(
        sync_dispatcher.run,
        trigger=IntervalTrigger(minutes=sync_dispatcher.INTERVAL_MINUTES),
        id="sync_dispatcher",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )
    _scheduler.add_job(
        qitech_jobs_poll.run,
        trigger=IntervalTrigger(minutes=qitech_jobs_poll.INTERVAL_MINUTES),
        id="qitech_jobs_poll",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )
    _scheduler.add_job(
        backfill_worker.run,
        trigger=IntervalTrigger(seconds=backfill_worker.INTERVAL_SECONDS),
        id="backfill_worker",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )
    reconciler_minutes = reconciler.get_interval_minutes()
    _scheduler.add_job(
        reconciler.run,
        trigger=IntervalTrigger(minutes=reconciler_minutes),
        id="reconciler",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,  # 5 min — reconciler nao e urgente
    )
    _scheduler.start()
    logger.info(
        "scheduler started: sync_dispatcher every %s min, "
        "qitech_jobs_poll every %s min, backfill_worker every %s s, "
        "reconciler every %s min",
        sync_dispatcher.INTERVAL_MINUTES,
        qitech_jobs_poll.INTERVAL_MINUTES,
        backfill_worker.INTERVAL_SECONDS,
        reconciler_minutes,
    )
    return _scheduler


def shutdown_scheduler() -> None:
    """Para o scheduler; chamado no lifespan do app."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler stopped")
