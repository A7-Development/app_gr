"""Orquestrador de ciclo de sync.

Responsabilidades:
- Descobrir quais tenants tem a fonte habilitada (via `eligibility.list_enabled_configs`).
- Resolver o adapter correspondente ao `source_type` (registry local).
- Decifrar a config do tenant e passar para o adapter.
- Isolar falhas por tenant (um tenant quebrar nao derruba o ciclo).

O scheduler ([app/scheduler/jobs/bitfin_sync.py]) apenas chama `run_sync_cycle` —
toda logica de elegibilidade/config/adapter fica aqui.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.core.enums import SourceType
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.modules.integracoes.adapters.erp.bitfin.etl import sync_all as bitfin_sync_all
from app.modules.integracoes.services.eligibility import list_enabled_configs
from app.modules.integracoes.services.source_config import decrypt_config

logger = logging.getLogger("gr.integracoes.sync_runner")

# Assinatura do entrypoint de adapter: (tenant_id, config_dict, since) -> summary dict
AdapterEntrypoint = Callable[[UUID, dict, date | None], Awaitable[dict[str, Any]]]


async def _run_bitfin(
    tenant_id: UUID, config_dict: dict, since: date | None
) -> dict[str, Any]:
    config = BitfinConfig.from_dict(config_dict)
    return await bitfin_sync_all(tenant_id, config, since=since)


_ADAPTER_REGISTRY: dict[SourceType, AdapterEntrypoint] = {
    SourceType.ERP_BITFIN: _run_bitfin,
}


async def run_sync_cycle(
    source_type: SourceType, *, since: date | None = None
) -> list[dict[str, Any]]:
    """Executa um ciclo completo de sync para a fonte `source_type`.

    Itera todos os tenants com `tenant_source_config.enabled=true` para essa fonte,
    chama o adapter registrado em `_ADAPTER_REGISTRY`. Retorna lista de summaries
    (um por tenant processado, inclusive os que falharam).
    """
    adapter = _ADAPTER_REGISTRY.get(source_type)
    if adapter is None:
        raise ValueError(f"Nenhum adapter registrado para source_type={source_type.value}")

    async with AsyncSessionLocal() as db:
        configs = await list_enabled_configs(db, source_type)

    if not configs:
        logger.info("sync_cycle: source=%s sem tenants elegiveis", source_type.value)
        return []

    summaries: list[dict[str, Any]] = []
    for cfg in configs:
        logger.info(
            "sync_cycle: start tenant=%s source=%s", cfg.tenant_id, source_type.value
        )
        try:
            plain = decrypt_config(cfg.config)
            summary = await adapter(cfg.tenant_id, plain, since)
            summaries.append(summary)
            logger.info(
                "sync_cycle: done tenant=%s source=%s elapsed=%s errors=%s",
                cfg.tenant_id,
                source_type.value,
                summary.get("elapsed_seconds"),
                len(summary.get("errors", [])),
            )
        except Exception:
            logger.exception(
                "sync_cycle: fatal tenant=%s source=%s", cfg.tenant_id, source_type.value
            )
    return summaries
