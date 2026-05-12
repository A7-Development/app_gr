"""APScheduler tick: processa proximo backfill_job pending (1 por tick).

Cadencia rapida (5s) pra dar feedback responsivo na UI. Cada tick pega 1
job pending — se houver — e processa serialmente todas as datas dele.

Multiple jobs (de endpoints diferentes) ficam na fila e sao processados
um por tick. Se voce criar 3 jobs em sequencia, eles rodam um a um — nao
em paralelo. Isso e proposital: 3 jobs paralelos pra mesma source/credencial
gera 3x throttle e nao acelera nada (limite e a API externa, nao nosso CPU).
"""

from __future__ import annotations

import logging
from typing import Any

from app.modules.integracoes.services.backfill_service import (
    process_next_pending_job,
)

logger = logging.getLogger("gr.scheduler.backfill")

INTERVAL_SECONDS: int = 5


async def run() -> dict[str, Any]:
    """Tick do worker. Logga summary quando faz algo, silencioso quando idle."""
    summary = await process_next_pending_job()
    if summary.get("picked_job_id"):
        logger.info(
            "backfill_worker: job=%s processed=%d ok=%d fail=%d elapsed=%.1fs",
            summary["picked_job_id"],
            summary["dates_processed"],
            summary["dates_succeeded"],
            summary["dates_failed"],
            summary["elapsed_seconds"],
        )
    return summary
