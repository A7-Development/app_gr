"""APScheduler tick: dispatcher da state machine de sync (F1.3).

Cadencia 1 min. Cada tick reclama orfaos, pega N rows due via lock, e
processa serialmente chamando run_sync_endpoint(since=data_referencia)
+ transition() pra cada uma.

Wrapper fino — toda logica em
`app.modules.integracoes.services.state_machine_dispatcher.dispatch_due`.

Pode rodar em paralelo com `reconciler`, `watermark_scanner` e
`recent_complete_refresher` legados — endpoints com `state_machine_enabled=
True` vivem APENAS no caminho da state machine (este job), os demais
continuam no caminho legado. Rollout gradual: liga endpoint por endpoint
via EndpointSpec.
"""

from __future__ import annotations

import logging
from typing import Any

from app.modules.integracoes.services.state_machine_dispatcher import (
    dispatch_due,
)

logger = logging.getLogger("gr.scheduler.state_machine")

INTERVAL_MINUTES: int = 1


async def run() -> dict[str, Any]:
    """Tick do dispatcher. Logga summary quando faz algo, silencioso quando idle."""
    summary = await dispatch_due()
    if summary.get("rows_picked"):
        logger.info(
            "state_machine_tick: picked=%d ok=%d skipped=%d errored=%d "
            "orphans=%d elapsed=%.1fs",
            summary["rows_picked"],
            summary["rows_processed_ok"],
            summary["rows_skipped_disabled"],
            summary["rows_errored"],
            summary["orphans_reclaimed"],
            summary["elapsed_seconds"],
        )
    elif summary.get("orphans_reclaimed"):
        logger.info(
            "state_machine_tick: idle, orphans reclaimed=%d",
            summary["orphans_reclaimed"],
        )
    return summary
