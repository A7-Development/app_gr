"""APScheduler setup — integrado ao lifespan do FastAPI."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.scheduler.jobs import bitfin_sync

logger = logging.getLogger("gr.scheduler")

_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler:
    """Instancia e inicia o scheduler; chamado no lifespan do app."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
    _scheduler.add_job(
        bitfin_sync.run,
        trigger=IntervalTrigger(minutes=bitfin_sync.INTERVAL_MINUTES),
        id="bitfin_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    _scheduler.start()
    logger.info(
        "scheduler started: bitfin_sync every %s minutes",
        bitfin_sync.INTERVAL_MINUTES,
    )
    return _scheduler


def shutdown_scheduler() -> None:
    """Para o scheduler; chamado no lifespan do app."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler stopped")
