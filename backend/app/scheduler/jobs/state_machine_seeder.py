"""APScheduler nightly: seeda rows NOT_STARTED na endpoint_date_state (F1.4).

Roda 1x/dia as 08:00 SP (apos watermark_scanner que e 06:00, dando tempo
do reconciler legado fazer seu trabalho antes da state machine entrar em
acao). Cria rows pra dias uteis no range [today-30bd, today+5bd] por
(tenant, source, env, ua, endpoint) com state_machine_enabled=True.

INSERT ON CONFLICT DO NOTHING — rerun no mesmo dia e idempotente.

Wrapper fino — toda logica em
`app.modules.integracoes.services.state_machine_seeder.seed_endpoint_date_states`.
"""

from __future__ import annotations

import logging
from typing import Any

from app.modules.integracoes.services.state_machine_seeder import (
    seed_endpoint_date_states,
)

logger = logging.getLogger("gr.scheduler.state_machine_seeder")

# 08:00 SP — apos watermark_scanner (06:00) e antes dos daily_at tipicos
# dos endpoints (09:00+). State machine tick (1 min) ja captura as rows
# imediatamente apos seed.
DAILY_HOUR: int = 8
DAILY_MINUTE: int = 0


async def run() -> dict[str, Any]:
    """Tick do seeder. Sempre logga summary (job diario, low-volume)."""
    summary = await seed_endpoint_date_states()
    logger.info(
        "state_machine_seeder: groups=%d endpoints_seeded=%d "
        "skipped=%d rows=%d elapsed=%.1fs",
        summary["groups_scanned"],
        summary["endpoints_seeded"],
        summary["endpoints_skipped_disabled"],
        summary["rows_inserted"],
        summary["elapsed_seconds"],
    )
    return summary
