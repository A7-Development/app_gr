"""Orquestrador de ciclo de sync.

Responsabilidades:
- Descobrir quais (tenant, ua) tem a fonte habilitada (via `eligibility.list_enabled_configs`).
- Resolver o adapter correspondente ao `source_type` via `_ADAPTER_REGISTRY`.
- Decifrar a config + passar para o adapter (ping ou sync).
- Isolar falhas por linha de config (uma UA quebrar nao derruba o ciclo).

Multi-UA (CLAUDE.md secao 13, 2026-04-25): cada linha de `tenant_source_config`
representa uma credencial — pode haver N por tenant na mesma fonte/ambiente,
uma por UA. O ciclo de sync itera por linha, nao por tenant.

O scheduler ([app/scheduler/jobs/bitfin_sync.py]) chama `run_sync_cycle`;
o endpoint admin ([routers/sources.py]) usa `run_sync_one` + `run_ping`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.adapter import (
    adapter_ping as qitech_ping,
)
from app.modules.integracoes.adapters.admin.qitech.adapter import (
    adapter_sync as qitech_sync,
)
from app.modules.integracoes.adapters.erp.bitfin.adapter import (
    adapter_ping as bitfin_ping,
)
from app.modules.integracoes.adapters.erp.bitfin.adapter import (
    adapter_sync as bitfin_sync,
)
from app.modules.integracoes.services.eligibility import list_enabled_configs
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
)

logger = logging.getLogger("gr.integracoes.sync_runner")

# Adapter contracts. Ping recebe config + tenant_id/environment/ua opcionais
# para adapters que precisam chavear cache ou contexto por (tenant, env, ua)
# (ex.: QiTech cacheia token por essa tripla). Adapters sem essa necessidade
# declaram `**_` para aceitar sem usar.
PingFn = Callable[..., Awaitable[dict[str, Any]]]
SyncFn = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class AdapterEntry:
    """Registered adapter for a source_type."""

    sync: SyncFn
    ping: PingFn


_ADAPTER_REGISTRY: dict[SourceType, AdapterEntry] = {
    SourceType.ERP_BITFIN: AdapterEntry(sync=bitfin_sync, ping=bitfin_ping),
    SourceType.ADMIN_QITECH: AdapterEntry(sync=qitech_sync, ping=qitech_ping),
}


def get_adapter(source_type: SourceType) -> AdapterEntry:
    """Resolve the adapter for `source_type`. Raises ValueError if absent."""
    adapter = _ADAPTER_REGISTRY.get(source_type)
    if adapter is None:
        raise ValueError(f"Nenhum adapter registrado para source_type={source_type.value}")
    return adapter


async def run_sync_cycle(
    source_type: SourceType,
    *,
    environment: Environment = Environment.PRODUCTION,
    since: date | None = None,
    triggered_by: str = "system:scheduler",
) -> list[dict[str, Any]]:
    """Executa um ciclo completo de sync para a fonte + ambiente.

    Itera todas as linhas com `tenant_source_config.enabled=true` (pode ser
    >1 por tenant em multi-UA), chama o adapter registrado por linha. Retorna
    lista de summaries (um por linha processada, inclusive os que falharam).
    """
    adapter = get_adapter(source_type)

    async with AsyncSessionLocal() as db:
        configs = await list_enabled_configs(db, source_type, environment)

    if not configs:
        logger.info(
            "sync_cycle: source=%s env=%s sem configs elegiveis",
            source_type.value,
            environment.value,
        )
        return []

    summaries: list[dict[str, Any]] = []
    for cfg in configs:
        logger.info(
            "sync_cycle: start tenant=%s ua=%s source=%s env=%s",
            cfg.tenant_id,
            cfg.unidade_administrativa_id,
            source_type.value,
            environment.value,
        )
        try:
            plain = decrypt_config(cfg.config)
            summary = await adapter.sync(
                cfg.tenant_id,
                plain,
                since,
                triggered_by=triggered_by,
                unidade_administrativa_id=cfg.unidade_administrativa_id,
            )
            summaries.append(summary)
            logger.info(
                "sync_cycle: done tenant=%s ua=%s source=%s elapsed=%s errors=%s",
                cfg.tenant_id,
                cfg.unidade_administrativa_id,
                source_type.value,
                summary.get("elapsed_seconds"),
                len(summary.get("errors", [])),
            )
        except Exception:
            logger.exception(
                "sync_cycle: fatal tenant=%s ua=%s source=%s",
                cfg.tenant_id,
                cfg.unidade_administrativa_id,
                source_type.value,
            )
    return summaries


async def run_sync_one(
    tenant_id: UUID,
    source_type: SourceType,
    *,
    environment: Environment = Environment.PRODUCTION,
    since: date | None = None,
    triggered_by: str = "system:api",
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """Dispara sync para uma config (tenant + fonte + UA). Nao verifica `enabled`.

    Usado pelo endpoint admin POST /integracoes/sources/{source_type}/sync.
    Propaga erros (diferente do cycle, que isola por linha) para que o
    operador veja a falha imediatamente.

    Multi-UA: `unidade_administrativa_id=None` busca a config legacy (linha
    sem UA preenchida). Caller que conhece a UA passa explicitamente.
    """
    adapter = get_adapter(source_type)
    async with AsyncSessionLocal() as db:
        row = await get_config(
            db,
            tenant_id,
            source_type,
            environment,
            unidade_administrativa_id=unidade_administrativa_id,
        )
    if row is None:
        raise ValueError(
            f"Tenant {tenant_id} nao tem tenant_source_config para "
            f"{source_type.value}/{environment.value}/ua={unidade_administrativa_id}"
        )
    plain = decrypt_config(row.config)
    return await adapter.sync(
        tenant_id,
        plain,
        since,
        triggered_by=triggered_by,
        unidade_administrativa_id=row.unidade_administrativa_id,
    )


async def run_ping(
    tenant_id: UUID,
    source_type: SourceType,
    *,
    environment: Environment = Environment.PRODUCTION,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """Chama `adapter.ping(config)` para a tupla (tenant, fonte, ambiente, ua).

    Retorna o resultado do ping (nunca levanta — erros viram ok=False no dict).
    """
    adapter = get_adapter(source_type)
    async with AsyncSessionLocal() as db:
        row = await get_config(
            db,
            tenant_id,
            source_type,
            environment,
            unidade_administrativa_id=unidade_administrativa_id,
        )
    if row is None:
        return {
            "ok": False,
            "detail": (
                f"sem config para {source_type.value}/{environment.value}/"
                f"ua={unidade_administrativa_id} neste tenant"
            ),
        }
    plain = decrypt_config(row.config)
    return await adapter.ping(
        plain,
        tenant_id=tenant_id,
        environment=environment,
        unidade_administrativa_id=row.unidade_administrativa_id,
    )
