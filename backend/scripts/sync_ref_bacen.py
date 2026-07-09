"""Sincroniza a referencia publica Bacen (ref_bacen_instituicao/agencia).

Fontes: CSV Participantes do STR + API Olinda Informes_Agencias. Idempotente
(upsert sem delete). Rodar mensalmente (agendamento via cron/APScheduler e
follow-up); on-demand quando o classificador reportar nao-resolvidos novos.

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
