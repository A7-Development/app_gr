"""Job APScheduler que dispara um ciclo de sync para a fonte `erp:bitfin`.

Delega toda a logica (elegibilidade, config por tenant, chamada do adapter) para
`integracoes.public.run_sync_cycle`. Aqui ficam apenas trigger + interval.

Registrado no lifespan do FastAPI (app/main.py). Intervalo default: 30 minutos.
Ajuste via env `BITFIN_SYNC_INTERVAL_MINUTES`.
"""

from __future__ import annotations

import logging
import os

from app.core.enums import SourceType
from app.modules.integracoes.public import run_sync_cycle

logger = logging.getLogger("gr.scheduler.bitfin_sync")

INTERVAL_MINUTES = int(os.getenv("BITFIN_SYNC_INTERVAL_MINUTES", "30"))


async def run() -> None:
    """Dispara ciclo de sync para erp:bitfin."""
    logger.info("bitfin_sync: triggering cycle")
    summaries = await run_sync_cycle(SourceType.ERP_BITFIN)
    logger.info("bitfin_sync: cycle done tenants_processed=%d", len(summaries))
