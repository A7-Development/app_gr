"""Drena a landing zone fiscal (NFe/CTe) para o warehouse — job agendado.

Diferente da cobranca, nao ha `tenant_source_config` fiscal: os proprios
labels pendentes em `file_landing` definem o trabalho (contrato = label).
Para cada tenant com pendencia em fiscal_nfe/fiscal_cte, spawna o subprocess
`scripts.run_fiscal_sync` (parse de XML e CPU-bound; o backfill inicial tem
~29k documentos). Idempotente por chave de acesso — re-execucao e inofensiva;
o guard de inflight evita spawns concorrentes do mesmo tenant.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.fiscal.etl import LABELS
from app.modules.integracoes.models.file_landing import FileLanding

logger = logging.getLogger(__name__)

INTERVAL_MINUTES = 5

# Tenants com subprocess vivo (guard de concorrencia) + refs dos wait()s.
_INFLIGHT: set[UUID] = set()
_RUNNING: set[asyncio.Task] = set()


async def run() -> None:
    async with AsyncSessionLocal() as db:
        tenants = (
            (
                await db.execute(
                    select(FileLanding.tenant_id)
                    .where(
                        FileLanding.source_label.in_(LABELS),
                        FileLanding.consumed_at.is_(None),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
    for tenant_id in tenants:
        if tenant_id in _INFLIGHT:
            continue
        await _dispatch(tenant_id)


async def _dispatch(tenant_id: UUID) -> None:
    logger.info("fiscal_landing: pendencias tenant=%s — disparando drain", tenant_id)
    backend_root = Path(__file__).resolve().parents[2]  # .../backend
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "scripts.run_fiscal_sync",
        str(tenant_id),
        cwd=str(backend_root),
        env=os.environ.copy(),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    _INFLIGHT.add(tenant_id)

    async def _wait() -> None:
        try:
            await proc.wait()
        finally:
            _INFLIGHT.discard(tenant_id)

    task = asyncio.create_task(_wait())
    _RUNNING.add(task)
    task.add_done_callback(_RUNNING.discard)
