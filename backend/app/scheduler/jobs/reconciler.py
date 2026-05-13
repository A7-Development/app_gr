"""APScheduler tick: reconciler do auto-heal QiTech (Fase 1).

Periodicamente compara estado-real (linhas em wh_qitech_raw_relatorio na
janela) vs estado-desejado (todos os dias uteis ANBIMA devem estar
coletados). Pra cada (tenant, ua, endpoint) com `gap`, enfileira
BackfillJob. Worker existente (`backfill_worker.py`) processa.

Cadencia raras propositais — 30 min (ver `Settings.RECONCILER_TICK_MINUTES`).
Quase nao compete com `sync_dispatcher` (que cuida da cadencia normal,
1 min). Reconciler e segunda linha de defesa.

Idempotente: skip por job ativo + dedupe de datas no BackfillJob.create.

Detalhes em `app/modules/integracoes/services/reconciler.py`.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.modules.integracoes.services.reconciler import run_reconciler_tick

logger = logging.getLogger("gr.scheduler.reconciler")


def get_interval_minutes() -> int:
    """Le do settings (suporta override via env)."""
    return get_settings().RECONCILER_TICK_MINUTES


async def run() -> dict[str, Any]:
    """Tick do reconciler. Logga summary quando enfileira algo."""
    summary = await run_reconciler_tick()
    if summary.get("skipped"):
        return summary
    if summary.get("gaps_detected", 0) > 0 or summary.get("jobs_failed", 0) > 0:
        logger.info(
            "reconciler: gaps=%d enqueued=%d failed=%d elapsed=%.1fs",
            summary["gaps_detected"],
            summary["jobs_enqueued"],
            summary["jobs_failed"],
            summary["elapsed_seconds"],
        )
    return summary
