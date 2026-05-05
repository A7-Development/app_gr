"""Sync dispatcher — registers `tenant_source_config.sync_frequency_minutes`
as the source of truth for ETL cadence.

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

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.integracoes.public import (
    list_enabled_configs,
    rule_name_for,
    run_sync_one,
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
    """Tick do dispatcher. Returns summary com contadores pra observabilidade."""
    started_at = datetime.now(UTC)
    summary = {
        "configs_scanned": 0,
        "dispatched": 0,
        "skipped_not_due": 0,
        "skipped_no_rule": 0,
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

                    last_attempt = await last_sync_attempt_at(
                        db, cfg.tenant_id, rule_or_model=rule
                    )
                    threshold = timedelta(minutes=cfg.sync_frequency_minutes)
                    if (
                        last_attempt is not None
                        and (started_at - last_attempt) < threshold
                    ):
                        summary["skipped_not_due"] += 1
                        continue

                    logger.info(
                        "dispatch: tenant=%s source=%s env=%s ua=%s "
                        "freq_min=%s last_attempt=%s",
                        cfg.tenant_id,
                        source_type.value,
                        env.value,
                        cfg.unidade_administrativa_id,
                        cfg.sync_frequency_minutes,
                        last_attempt,
                    )
                    summary["dispatched"] += 1
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

    return summary


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
