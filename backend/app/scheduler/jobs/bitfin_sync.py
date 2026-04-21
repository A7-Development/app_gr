"""Job APScheduler que executa `sync_all` do adapter Bitfin para todos os tenants ativos.

Registrado no lifespan do FastAPI (app/main.py). Intervalo default: 30 minutos.
Ajuste via env `BITFIN_SYNC_INTERVAL_MINUTES`.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.erp.bitfin.etl import sync_all
from app.shared.identity.tenant import Tenant

logger = logging.getLogger("gr.scheduler.bitfin_sync")

INTERVAL_MINUTES = int(os.getenv("BITFIN_SYNC_INTERVAL_MINUTES", "30"))


async def run() -> None:
    """Executa sync_all para cada tenant ativo."""
    async with AsyncSessionLocal() as db:
        stmt = select(Tenant).where(Tenant.ativo.is_(True))
        tenants = (await db.execute(stmt)).scalars().all()
    for t in tenants:
        logger.info("bitfin_sync: start tenant=%s", t.slug)
        try:
            summary = await sync_all(t.id, since=None)
            logger.info(
                "bitfin_sync: done tenant=%s elapsed=%s tables=%s errors=%s",
                t.slug,
                summary.get("elapsed_seconds"),
                len(summary.get("tables", [])),
                len(summary.get("errors", [])),
            )
        except Exception:
            logger.exception("bitfin_sync: fatal tenant=%s", t.slug)
