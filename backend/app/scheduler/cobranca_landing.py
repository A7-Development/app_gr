"""Drena a landing zone de cobranca (CNAB) para o pipeline — job agendado.

Fecha o gap do piloto A7 (2026-07-07): o silver de cobranca so era populado
pelo botao "Sincronizar" da pagina banco-cobrador (parou 15 dias sem ninguem
clicar). Este job roda a cada ciclo e, para cada tenant cuja fonte COBRANCA
esta no modo `landing`, dispara o MESMO ciclo do botao (subprocess detached
`scripts.run_cobranca_sync` — CPU-bound, nao pode rodar no event loop)
quando ha arquivos pendentes em `file_landing`.

O botao continua existindo como "forcar agora"; o run row em
`wh_cobranca_sync_run` e o mesmo — a pagina enxerga execucoes agendadas e
manuais no mesmo polling (§7.3).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.filesource.landing import _labels
from app.modules.integracoes.models.file_landing import FileLanding
from app.modules.integracoes.models.tenant_source_config import TenantSourceConfig
from app.modules.integracoes.services.source_config import decrypt_config
from app.warehouse.cnab_raw_arquivo import FILE_SOURCE_LANDING
from app.warehouse.cobranca_sync_run import SYNC_STATUS_RUNNING, CobrancaSyncRun

logger = logging.getLogger(__name__)

INTERVAL_MINUTES = 5
# Espelha o _STUCK_APOS do endpoint: run sem heartbeat ha 3min = morto.
_STUCK_APOS = timedelta(minutes=3)

# Referencias fortes aos wait()s dos subprocessos (evita GC do task).
_RUNNING: set[asyncio.Task] = set()


async def run() -> None:
    """Um tick do drain: verifica cada tenant em modo landing e dispara."""
    async with AsyncSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(TenantSourceConfig).where(
                        TenantSourceConfig.source_type == SourceType.COBRANCA,
                        TenantSourceConfig.environment == Environment.PRODUCTION,
                        TenantSourceConfig.enabled.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        candidatos: list[tuple[UUID, list[str]]] = []
        for row in rows:
            try:
                config = decrypt_config(row.config)
            except Exception:
                logger.exception("config de cobranca indecifravel tenant=%s", row.tenant_id)
                continue
            fs_cfg = (config or {}).get("file_source") or {}
            if fs_cfg.get("mode") != FILE_SOURCE_LANDING:
                continue
            candidatos.append((row.tenant_id, _labels(fs_cfg)))

        for tenant_id, labels in candidatos:
            await _maybe_dispatch(db, tenant_id, labels)


async def _maybe_dispatch(db, tenant_id: UUID, labels: list[str]) -> None:
    pendentes = (
        await db.execute(
            select(func.count())
            .select_from(FileLanding)
            .where(
                FileLanding.tenant_id == tenant_id,
                FileLanding.source_label.in_(labels),
                FileLanding.consumed_at.is_(None),
            )
        )
    ).scalar_one()
    if not pendentes:
        return

    now = datetime.now(UTC)
    em_curso = (
        await db.execute(
            select(CobrancaSyncRun.id).where(
                CobrancaSyncRun.tenant_id == tenant_id,
                CobrancaSyncRun.status == SYNC_STATUS_RUNNING,
                CobrancaSyncRun.heartbeat_at > now - _STUCK_APOS,
            )
        )
    ).first()
    if em_curso is not None:
        return  # run vivo (manual ou agendado) ja vai drenar

    run_row = CobrancaSyncRun(
        id=uuid4(),
        tenant_id=tenant_id,
        status=SYNC_STATUS_RUNNING,
        fase="coleta",
        started_at=now,
        heartbeat_at=now,
        triggered_by="scheduler:cobranca_landing",
    )
    db.add(run_row)
    await db.commit()

    logger.info(
        "cobranca_landing: %d pendente(s) tenant=%s — disparando sync run=%s",
        pendentes,
        tenant_id,
        run_row.id,
    )
    backend_root = Path(__file__).resolve().parents[2]  # .../backend
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "scripts.run_cobranca_sync",
        str(tenant_id),
        str(run_row.id),
        cwd=str(backend_root),
        env=os.environ.copy(),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    task = asyncio.create_task(proc.wait())
    _RUNNING.add(task)
    task.add_done_callback(_RUNNING.discard)
