"""Sincroniza a referencia publica Bacen (ref_bacen_instituicao/agencia).

Fontes: CSV Participantes do STR + API Olinda Informes_Agencias + Relacao de
Instituicoes em Funcionamento (segmento oficial) + Informes_PostosDeAtendimento.
Idempotente (upsert sem delete). O agendamento e AUTOMATICO via APScheduler
(`app/scheduler/ref_bacen_sync.py`, diario 05:30 SP) — este script permanece
para execucao on-demand/manual (backfill, debug).

Uso (de backend/):
    .venv/bin/python scripts/sync_ref_bacen.py
"""

from __future__ import annotations

import asyncio
import logging

import app.metadata  # noqa: F401  -- registry SQLAlchemy completo (FK decision_log/tenants)
from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.data.bacen.etl import sync_ref_bacen

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        metricas = await sync_ref_bacen(db)
    print(metricas)


if __name__ == "__main__":
    asyncio.run(main())
