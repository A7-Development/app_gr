"""Cron do monitoramento SERPRO NF-e (F3) -- tick por tenant configurado.

Por que cron alem do webhook:
1. O push do SERPRO NAO tem fila/retry — ping perdido so volta com evento
   novo. A auditoria de entrega (`entregue`/`dataEntrega` por chave) pesca
   o que nao processamos, sem custo de consulta.
2. Solicitacoes expiram em 30 dias — o tick re-inscreve as chaves ativas
   ~5 dias antes.
3. Chaves novas entram no escopo (duplicata a vencer) continuamente — o
   tick enrola e inscreve.

O que o tick NAO faz: reconsultar chaves em massa (custo). Consulta paga
so acontece via ping do webhook ou auditoria que detectou aviso perdido.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.data.serpro.errors import SerproError
from app.modules.integracoes.adapters.data.serpro.monitoring import (
    ciclo_monitoramento,
)
from app.modules.integracoes.models.tenant_source_config import TenantSourceConfig

logger = logging.getLogger("gr.integracoes.serpro.monitor")

# 1x por hora: enrolamento/renovacao nao precisam de mais; a latencia de
# deteccao vem do webhook, nao deste tick.
INTERVAL_MINUTES: int = 60


async def run_serpro_monitor_cycle() -> None:
    """Roda o ciclo para todo tenant com DATA_SERPRO_NFE habilitada."""
    async with AsyncSessionLocal() as db:
        tenant_ids = (
            (
                await db.execute(
                    select(TenantSourceConfig.tenant_id).where(
                        TenantSourceConfig.source_type
                        == SourceType.DATA_SERPRO_NFE,
                        TenantSourceConfig.environment == Environment.PRODUCTION,
                        TenantSourceConfig.enabled.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )

    for tenant_id in tenant_ids:
        async with AsyncSessionLocal() as db:
            try:
                await ciclo_monitoramento(db, tenant_id)
            except SerproError as e:
                logger.warning(
                    "serpro monitor tenant=%s falhou: %s", tenant_id, e
                )
            except Exception:
                logger.exception(
                    "serpro monitor tenant=%s erro inesperado", tenant_id
                )
