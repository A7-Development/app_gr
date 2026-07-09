"""Sync agendado da referencia publica Bacen — job APScheduler.

Fonte global (sem tenant): STR (participantes) + Informes_Agencias + Relacao de
Instituicoes em Funcionamento (segmento oficial) + Informes_PostosDeAtendimento.
Upsert SEM delete (idempotente); os snapshots Olinda sao mensais, entao rodar
1x/dia e barato e mantem a ref fresca sem depender de trigger manual.

Substitui o disparo manual de `scripts/sync_ref_bacen.py`. A execucao grava
DecisionLog (§14.5) — visivel no Painel de Saude das Integracoes
(/admin/dados/saude), fonte `ref_bacen_adapter`.
"""

from __future__ import annotations

import logging

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.data.bacen.etl import sync_ref_bacen

logger = logging.getLogger(__name__)

# Diario as 05:30 SP — antes do watermark_scanner (06:00) e dos daily_at dos
# endpoints (07:00). Snapshot Bacen e mensal; o custo de rodar diario e minimo
# (upsert idempotente) e garante frescor sem gate manual.
DAILY_HOUR = 5
DAILY_MINUTE = 30


async def run() -> None:
    """Um ciclo completo de sync da referencia Bacen."""
    try:
        async with AsyncSessionLocal() as db:
            metricas = await sync_ref_bacen(db)
        logger.info("ref_bacen_sync: %s", metricas)
    except Exception:
        logger.exception("ref_bacen_sync falhou")
