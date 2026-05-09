"""Sync dispatcher — descobre quais syncs disparar a cada tick.

Modo de operacao decidido pela feature flag
`INTEGRACOES_USE_ENDPOINT_SCHEDULING` (CLAUDE.md §13 + plano refactor
2026-05-05):

- **Flag False (default, modo legado)**: `tenant_source_config.sync_frequency_minutes`
  e a fonte da verdade. Dispara `run_sync_one(tenant, source, ...)`.
- **Flag True (modo novo)**: `tenant_source_endpoint_config` e a fonte da
  verdade — granularidade fina por endpoint. Dispara
  `run_sync_endpoint(tenant, source, endpoint_name, ...)`.

Modo legado abaixo (texto original):
==========================================================================
Tica como `tenant_source_config.sync_frequency_minutes` ditando cadencia.

Tica a cada minuto. A cada tick:
  1. SELECT em tenant_source_config WHERE enabled=true E
     sync_frequency_minutes IS NOT NULL (ambiente PRODUCTION + tenant ativo).
  2. Pra cada linha (1 por (tenant, source, env, ua)):
     a. Le `last_sync_attempt_at` no decision_log pro adapter dessa fonte.
        OBS: chave por (tenant, rule) — em multi-UA nao distingue UA, vide
        nota abaixo.
     b. Se nunca rodou OU passou >= sync_frequency_minutes desde a ultima
        tentativa, dispara `run_sync_one(tenant, source_type, env, ua)` em
        background (asyncio.create_task), sem await — proximo tick continua.
     c. Caso contrario, ignora (proximo tick reavalia).

Por que `last_sync_attempt_at` e nao `last_sync_at` (so OK):
  Se um sync falha, queremos respeitar o intervalo do operador antes do retry
  — caso contrario o dispatcher martelaria a API toda execucao do tick (1
  min) ate dar OK. Falha registra entry SYNC com explanation != 'OK', e isso
  conta como tentativa pro proposito do intervalo.

Multi-UA caveat:
  `last_sync_attempt_at(tenant, rule)` nao filtra por UA — entao se o tenant
  tem 2 UAs e uma sincou recem, a outra fica esperando. Tradeoff aceito pra
  MVP: simplificacao da query + decisao_log nao tem UA gravada hoje. Quando
  multi-UA ficar load-bearing, mover proveniencia de "ultimo sync" pra
  coluna em `tenant_source_config` (atualizada pelo proprio adapter).

Concurrency:
  - APScheduler garante 1 instancia do tick por vez (`max_instances=1`).
  - Dentro do tick, `run_sync_one` roda em `asyncio.create_task` — multiplas
    fontes podem sincar em paralelo. Adapter individualmente lida com seu
    rate limit / connection pool. Bitfin (SQL Server) ja serializa por
    pyodbc thread executor.

Substitui o antigo `app/scheduler/jobs/bitfin_sync.py`, que era hardcoded
em 30 min e ignorava `tenant_source_config.sync_frequency_minutes`. Agora
o valor da tabela ditta a cadencia — UI vai ganhar editor (PR 2).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.public import (
    list_enabled_configs,
    rule_name_for,
    run_sync_endpoint,
    run_sync_one,
)
from app.modules.integracoes.services.endpoint_scheduling import (
    list_due_endpoints,
)
from app.shared.audit_log.sync_health import last_sync_attempt_at

logger = logging.getLogger("gr.scheduler.sync_dispatcher")

# Tick do dispatcher. 1 min da precisao real pra cadencia do operador
# (ex.: config 15 min vira 15-16 min, nao 15-19). Custo: 1 SELECT pequeno
# por minuto — desprezivel.
INTERVAL_MINUTES: int = 1

# Tasks em execucao (asyncio.create_task) — manter referencia forte pra
# evitar GC prematuro (ruff RUF006). Cada task remove a si mesma via
# done_callback quando finaliza.
_RUNNING_TASKS: set[asyncio.Task] = set()

# Lock in-flight por (tenant_id, source_type, ua_id). Antes de criar uma task
# nova, conferimos que essa chave nao esta rodando — sem isso, sync que
# demorava mais que `sync_frequency_minutes` causava reentrada (entry SYNC do
# `decision_log` so chega no fim, entao o tick subsequente "via" o timestamp
# antigo e disparava nova task). Combinado com o carimbo de
# `tenant_source_config.last_sync_started_at` (escrito no inicio em
# `sync_runner._mark_sync_started`), fecha as duas portas: o lock cobre
# concorrencia neste processo, started_at cobre operadores externos via API
# admin disparando sync sob demanda.
SyncKey = tuple[UUID, SourceType, UUID | None]
_INFLIGHT_KEYS: set[SyncKey] = set()

# Lock in-flight para o modo per-endpoint. Chave inclui `endpoint_name` para
# que multiplos endpoints da mesma fonte/tenant rodem em paralelo (ex.:
# bank_account.balance + market.outros_fundos do mesmo tenant — recursos
# diferentes na QiTech, podem rodar simultaneo).
EndpointSyncKey = tuple[UUID, SourceType, UUID | None, str]
_INFLIGHT_KEYS_ENDPOINT: set[EndpointSyncKey] = set()

# Ambientes que o dispatcher cobre. Sandbox so roda quando operador dispara
# manualmente via /integracoes/sources/<src>/sync — automacao de sandbox
# nao gera valor.
_ENVIRONMENTS = [Environment.PRODUCTION]

# Source types que o dispatcher conhece. Lista derivada do registro de
# adapters (sync_runner._ADAPTER_REGISTRY) — qualquer source novo precisa
# tanto de adapter registrado quanto de nome em RULE_NAME_BY_SOURCE.
# Calculado lazy no primeiro tick pra evitar import-time circular.
_KNOWN_SOURCES_CACHE: list | None = None


def _known_sources() -> list:
    global _KNOWN_SOURCES_CACHE
    if _KNOWN_SOURCES_CACHE is None:
        from app.modules.integracoes.services.sync_runner import (
            RULE_NAME_BY_SOURCE,
        )

        _KNOWN_SOURCES_CACHE = list(RULE_NAME_BY_SOURCE.keys())
    return _KNOWN_SOURCES_CACHE


async def run() -> dict[str, int]:
    """Tick do dispatcher. Roteador entre modo legado e modo per-endpoint.

    Modo decidido pela feature flag `INTEGRACOES_USE_ENDPOINT_SCHEDULING`
    (default False = legado). Veja docstring do modulo.
    """
    if get_settings().INTEGRACOES_USE_ENDPOINT_SCHEDULING:
        return await _run_endpoint_mode()
    return await _run_legacy_mode()


async def _run_legacy_mode() -> dict[str, int]:
    """Modo legado — itera tenant_source_config por source_type."""
    started_at = datetime.now(UTC)
    summary = {
        "mode": "legacy",
        "configs_scanned": 0,
        "dispatched": 0,
        "skipped_not_due": 0,
        "skipped_no_rule": 0,
        "skipped_in_flight": 0,
    }

    async with AsyncSessionLocal() as db:
        for env in _ENVIRONMENTS:
            for source_type in _known_sources():
                rule = rule_name_for(source_type)
                if rule is None:
                    summary["skipped_no_rule"] += 1
                    continue

                configs = await list_enabled_configs(db, source_type, env)
                for cfg in configs:
                    summary["configs_scanned"] += 1
                    if cfg.sync_frequency_minutes is None:
                        # null = sob demanda, dispatcher nao toca.
                        continue

                    key: SyncKey = (
                        cfg.tenant_id,
                        source_type,
                        cfg.unidade_administrativa_id,
                    )
                    if key in _INFLIGHT_KEYS:
                        # Sync anterior desta chave ainda nao terminou neste
                        # processo. Lock previne reentrada — espera proximo tick.
                        summary["skipped_in_flight"] += 1
                        logger.warning(
                            "skip in-flight: tenant=%s source=%s env=%s ua=%s",
                            cfg.tenant_id,
                            source_type.value,
                            env.value,
                            cfg.unidade_administrativa_id,
                        )
                        continue

                    last_attempt = await last_sync_attempt_at(
                        db, cfg.tenant_id, rule_or_model=rule
                    )
                    # Considera tambem `last_sync_started_at` da config — fica
                    # carimbado em `sync_runner._mark_sync_started` ANTES de
                    # `adapter.sync`, enquanto `last_sync_attempt_at` so e
                    # gravado no FIM (decision_log). Sem isso, restart entre
                    # processos via admin API podia dispatch um cycle ja em
                    # andamento iniciado por outro processo.
                    candidates = [
                        ts for ts in (last_attempt, cfg.last_sync_started_at) if ts is not None
                    ]
                    last_event = max(candidates) if candidates else None
                    threshold = timedelta(minutes=cfg.sync_frequency_minutes)
                    if (
                        last_event is not None
                        and (started_at - last_event) < threshold
                    ):
                        summary["skipped_not_due"] += 1
                        continue

                    logger.info(
                        "dispatch: tenant=%s source=%s env=%s ua=%s "
                        "freq_min=%s last_attempt=%s last_started=%s",
                        cfg.tenant_id,
                        source_type.value,
                        env.value,
                        cfg.unidade_administrativa_id,
                        cfg.sync_frequency_minutes,
                        last_attempt,
                        cfg.last_sync_started_at,
                    )
                    summary["dispatched"] += 1
                    _INFLIGHT_KEYS.add(key)
                    task = asyncio.create_task(
                        _run_one_safe(
                            tenant_id=cfg.tenant_id,
                            source_type=source_type,
                            environment=env,
                            ua_id=cfg.unidade_administrativa_id,
                        )
                    )
                    _RUNNING_TASKS.add(task)
                    task.add_done_callback(_RUNNING_TASKS.discard)
                    task.add_done_callback(
                        lambda _t, k=key: _INFLIGHT_KEYS.discard(k)
                    )

    return summary


async def _run_endpoint_mode() -> dict[str, int]:
    """Modo per-endpoint — itera tenant_source_endpoint_config.

    Usa `list_due_endpoints` que ja resolve a logica de schedule
    (interval/daily_at). Para cada linha due, dispara
    `run_sync_endpoint(tenant, source, endpoint_name, ...)` em background.
    """
    started_at = datetime.now(UTC)
    summary = {
        "mode": "endpoint",
        "endpoints_scanned": 0,
        "dispatched": 0,
        "skipped_in_flight": 0,
    }

    async with AsyncSessionLocal() as db:
        rows = await list_due_endpoints(
            db, now=started_at, environments=tuple(_ENVIRONMENTS)
        )
    summary["endpoints_scanned"] = len(rows)

    for row in rows:
        key: EndpointSyncKey = (
            row.tenant_id,
            row.source_type,
            row.unidade_administrativa_id,
            row.endpoint_name,
        )
        if key in _INFLIGHT_KEYS_ENDPOINT:
            summary["skipped_in_flight"] += 1
            logger.warning(
                "skip in-flight (endpoint): tenant=%s source=%s ua=%s endpoint=%s",
                row.tenant_id,
                row.source_type.value,
                row.unidade_administrativa_id,
                row.endpoint_name,
            )
            continue

        logger.info(
            "dispatch (endpoint): tenant=%s source=%s ua=%s endpoint=%s "
            "kind=%s value=%s last_started=%s",
            row.tenant_id,
            row.source_type.value,
            row.unidade_administrativa_id,
            row.endpoint_name,
            row.schedule_kind,
            row.schedule_value,
            row.last_sync_started_at,
        )
        summary["dispatched"] += 1
        _INFLIGHT_KEYS_ENDPOINT.add(key)
        task = asyncio.create_task(
            _run_endpoint_safe(
                tenant_id=row.tenant_id,
                source_type=row.source_type,
                environment=row.environment,
                ua_id=row.unidade_administrativa_id,
                endpoint_name=row.endpoint_name,
            )
        )
        _RUNNING_TASKS.add(task)
        task.add_done_callback(_RUNNING_TASKS.discard)
        task.add_done_callback(
            lambda _t, k=key: _INFLIGHT_KEYS_ENDPOINT.discard(k)
        )

    return summary


async def _run_endpoint_safe(
    *, tenant_id, source_type, environment, ua_id, endpoint_name
) -> None:
    """Wrapper que isola exceptions — falha de um endpoint nao quebra o tick."""
    try:
        await run_sync_endpoint(
            tenant_id,
            source_type,
            endpoint_name,
            environment=environment,
            triggered_by="system:scheduler",
            unidade_administrativa_id=ua_id,
        )
    except Exception:
        logger.exception(
            "sync_dispatcher (endpoint): run_sync_endpoint falhou "
            "tenant=%s source=%s ua=%s endpoint=%s",
            tenant_id,
            source_type.value,
            ua_id,
            endpoint_name,
        )


async def _run_one_safe(*, tenant_id, source_type, environment, ua_id) -> None:
    """Wrapper que isola exceptions — falha de uma config nao quebra o tick."""
    try:
        await run_sync_one(
            tenant_id,
            source_type,
            environment=environment,
            triggered_by="system:scheduler",
            unidade_administrativa_id=ua_id,
        )
    except Exception:
        logger.exception(
            "sync_dispatcher: run_sync_one falhou tenant=%s source=%s ua=%s",
            tenant_id,
            source_type.value,
            ua_id,
        )
