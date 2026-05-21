"""Orquestrador de ciclo de sync.

Responsabilidades:
- Descobrir quais (tenant, ua) tem a fonte habilitada (via `eligibility.list_enabled_configs`).
- Resolver o adapter correspondente ao `source_type` via `_ADAPTER_REGISTRY`.
- Decifrar a config + passar para o adapter (ping ou sync).
- Isolar falhas por linha de config (uma UA quebrar nao derruba o ciclo).

Multi-UA (CLAUDE.md secao 13, 2026-04-25): cada linha de `tenant_source_config`
representa uma credencial — pode haver N por tenant na mesma fonte/ambiente,
uma por UA. O ciclo de sync itera por linha, nao por tenant.

O scheduler ([app/scheduler/sync_dispatcher.py]) chama `run_sync_one` por
linha (cadencia em `tenant_source_config.sync_frequency_minutes`); o endpoint
admin ([routers/sources.py]) usa `run_sync_one` + `run_ping` para acoes
sob demanda.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.adapter import (
    adapter_ping as qitech_ping,
)
from app.modules.integracoes.adapters.admin.qitech.adapter import (
    adapter_sync as qitech_sync,
)
from app.modules.integracoes.adapters.admin.qitech.adapter import (
    adapter_sync_endpoint as qitech_sync_endpoint,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.adapter import (
    adapter_ping as serasa_pj_ping,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.adapter import (
    adapter_sync as serasa_pj_sync,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.adapter import (
    adapter_sync_endpoint as serasa_pj_sync_endpoint,
)
from app.modules.integracoes.adapters.erp.bitfin.adapter import (
    adapter_ping as bitfin_ping,
)
from app.modules.integracoes.adapters.erp.bitfin.adapter import (
    adapter_sync as bitfin_sync,
)
from app.modules.integracoes.adapters.erp.bitfin.adapter import (
    adapter_sync_endpoint as bitfin_sync_endpoint,
)
from app.modules.integracoes.models.tenant_source_config import TenantSourceConfig
from app.modules.integracoes.models.tenant_source_endpoint_config import (
    TenantSourceEndpointConfig,
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
SyncEndpointFn = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class AdapterEntry:
    """Registered adapter for a source_type.

    `sync`           — interface legada (sincroniza tudo). Usada quando flag
                       INTEGRACOES_USE_ENDPOINT_SCHEDULING=False (default).
    `sync_endpoint`  — interface nova per-endpoint. Usada quando flag liga.
    `ping`           — sanity check de credenciais (sem mudanca).
    """

    sync: SyncFn
    sync_endpoint: SyncEndpointFn
    ping: PingFn


_ADAPTER_REGISTRY: dict[SourceType, AdapterEntry] = {
    SourceType.ERP_BITFIN: AdapterEntry(
        sync=bitfin_sync,
        sync_endpoint=bitfin_sync_endpoint,
        ping=bitfin_ping,
    ),
    SourceType.ADMIN_QITECH: AdapterEntry(
        sync=qitech_sync,
        sync_endpoint=qitech_sync_endpoint,
        ping=qitech_ping,
    ),
    # Bureau: ping autentica de verdade; sync* e stub explicativo (consultas
    # sao sob demanda via workflow do credito, nao periodicas). Catalogo de
    # endpoint vazio — dispatcher nao chama sync_endpoint para Serasa.
    SourceType.BUREAU_SERASA_PJ: AdapterEntry(
        sync=serasa_pj_sync,
        sync_endpoint=serasa_pj_sync_endpoint,
        ping=serasa_pj_ping,
    ),
}

# Nome usado pelo adapter ao gravar `decision_log.rule_or_model`.
# Compartilhado entre router (`/runs`, `/last_sync_at`) e dispatcher
# (calcula proxima execucao a partir da ultima entry SYNC). Manter
# alinhado com `<adapter>.adapter_sync` (ex.: bitfin/etl.py:sync_all).
RULE_NAME_BY_SOURCE: dict[SourceType, str] = {
    SourceType.ERP_BITFIN: "bitfin_adapter",
    SourceType.ADMIN_QITECH: "qitech_adapter",
    SourceType.BUREAU_SERASA_PJ: "serasa_pj_adapter",
}


def get_adapter(source_type: SourceType) -> AdapterEntry:
    """Resolve the adapter for `source_type`. Raises ValueError if absent."""
    adapter = _ADAPTER_REGISTRY.get(source_type)
    if adapter is None:
        raise ValueError(f"Nenhum adapter registrado para source_type={source_type.value}")
    return adapter


async def _mark_sync_started(
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment,
    unidade_administrativa_id: UUID | None,
) -> None:
    """Carimba `tenant_source_config.last_sync_started_at = now()`.

    Chamado ANTES de `adapter.sync` (em `run_sync_one`/`run_sync_cycle`) para
    que o dispatcher veja "sync em andamento" mesmo enquanto a entry SYNC do
    `decision_log` ainda nao foi escrita (ela so chega no fim do ciclo).
    Combinado com o lock in-flight do dispatcher, fecha as duas portas para
    reentrada — lock cobre concorrencia no mesmo processo, started_at cobre
    restart entre processos / outros operadores via API.
    """
    stmt = update(TenantSourceConfig).where(
        TenantSourceConfig.tenant_id == tenant_id,
        TenantSourceConfig.source_type == source_type,
        TenantSourceConfig.environment == environment,
    )
    if unidade_administrativa_id is None:
        stmt = stmt.where(TenantSourceConfig.unidade_administrativa_id.is_(None))
    else:
        stmt = stmt.where(
            TenantSourceConfig.unidade_administrativa_id == unidade_administrativa_id
        )
    stmt = stmt.values(last_sync_started_at=datetime.now(UTC))
    async with AsyncSessionLocal() as db:
        await db.execute(stmt)
        await db.commit()


def rule_name_for(source_type: SourceType) -> str | None:
    """Devolve o `rule_or_model` do adapter, ou None se nao registrado."""
    return RULE_NAME_BY_SOURCE.get(source_type)


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
            await _mark_sync_started(
                cfg.tenant_id,
                source_type,
                environment,
                cfg.unidade_administrativa_id,
            )
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
    await _mark_sync_started(
        tenant_id, source_type, environment, row.unidade_administrativa_id
    )
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


# ─────────────────────────────────────────────────────────────────────────────
# Modo per-endpoint (CLAUDE.md §13 + plano refactor 2026-05-05)
# ─────────────────────────────────────────────────────────────────────────────


async def _mark_endpoint_sync_started(
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment,
    endpoint_name: str,
    unidade_administrativa_id: UUID | None,
) -> None:
    """Carimba `tenant_source_endpoint_config.last_sync_started_at = now()`
    + `last_sync_status = 'em_progresso'`. Chamado ANTES do handler.

    Espelha _mark_sync_started mas para a tabela TSEC. Granularidade fina
    para que o dispatcher veja "endpoint em andamento" via SQL sem precisar
    consultar lock in-memory.
    """
    stmt = update(TenantSourceEndpointConfig).where(
        TenantSourceEndpointConfig.tenant_id == tenant_id,
        TenantSourceEndpointConfig.source_type == source_type,
        TenantSourceEndpointConfig.environment == environment,
        TenantSourceEndpointConfig.endpoint_name == endpoint_name,
    )
    if unidade_administrativa_id is None:
        stmt = stmt.where(TenantSourceEndpointConfig.unidade_administrativa_id.is_(None))
    else:
        stmt = stmt.where(
            TenantSourceEndpointConfig.unidade_administrativa_id == unidade_administrativa_id
        )
    stmt = stmt.values(
        last_sync_started_at=datetime.now(UTC),
        last_sync_status="em_progresso",
        last_sync_error=None,
    )
    async with AsyncSessionLocal() as db:
        await db.execute(stmt)
        await db.commit()


async def _mark_endpoint_sync_finished(
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment,
    endpoint_name: str,
    unidade_administrativa_id: UUID | None,
    *,
    ok: bool,
    error_msg: str | None = None,
) -> None:
    """Carimba conclusao do sync no TSEC. ok=False grava error_msg em
    `last_sync_error` para mostrar na UI sem fazer JOIN com decision_log."""
    stmt = update(TenantSourceEndpointConfig).where(
        TenantSourceEndpointConfig.tenant_id == tenant_id,
        TenantSourceEndpointConfig.source_type == source_type,
        TenantSourceEndpointConfig.environment == environment,
        TenantSourceEndpointConfig.endpoint_name == endpoint_name,
    )
    if unidade_administrativa_id is None:
        stmt = stmt.where(TenantSourceEndpointConfig.unidade_administrativa_id.is_(None))
    else:
        stmt = stmt.where(
            TenantSourceEndpointConfig.unidade_administrativa_id == unidade_administrativa_id
        )
    stmt = stmt.values(
        last_sync_finished_at=datetime.now(UTC),
        last_sync_status="ok" if ok else "erro",
        last_sync_error=error_msg if not ok else None,
    )
    async with AsyncSessionLocal() as db:
        await db.execute(stmt)
        await db.commit()


async def run_sync_endpoint(
    tenant_id: UUID,
    source_type: SourceType,
    endpoint_name: str,
    *,
    environment: Environment = Environment.PRODUCTION,
    since: date | None = None,
    triggered_by: str = "system:scheduler",
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """Dispara sync para UM endpoint de uma config (tenant + fonte + UA).

    Diferenca de `run_sync_one`:
        - `run_sync_one`: chama `adapter.sync(...)` que sincroniza tudo da
          integracao. Usado em modo legado.
        - `run_sync_endpoint`: chama `adapter.sync_endpoint(name, ...)` que
          sincroniza UM endpoint. Usado pelo dispatcher modo novo + pela
          API admin POST /sources/{source}/endpoints/{name}/sync.

    Carimba TSEC.last_sync_* antes/depois. Levanta excecao se o tenant nao
    tem TSC pra source (sem credenciais nao da pra autenticar) — caller
    precisa garantir que TSC existe.

    Falhas dentro do adapter sao capturadas no proprio summary
    (`errors`/`ok`); aqui so reraise excecao se for falha total (ex.:
    credenciais ausentes, decrypt quebrou).
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
            f"{source_type.value}/{environment.value}/ua={unidade_administrativa_id} — "
            f"nao da pra sincronizar endpoint {endpoint_name!r}"
        )
    plain = decrypt_config(row.config)

    await _mark_endpoint_sync_started(
        tenant_id,
        source_type,
        environment,
        endpoint_name,
        row.unidade_administrativa_id,
    )

    summary: dict[str, Any]
    try:
        summary = await adapter.sync_endpoint(
            tenant_id,
            plain,
            endpoint_name,
            since=since,
            triggered_by=triggered_by,
            environment=environment,
            unidade_administrativa_id=row.unidade_administrativa_id,
        )
    except Exception as e:
        # Erro escapou do adapter — carimba TSEC e re-raise pra caller saber.
        await _mark_endpoint_sync_finished(
            tenant_id,
            source_type,
            environment,
            endpoint_name,
            row.unidade_administrativa_id,
            ok=False,
            error_msg=f"{type(e).__name__}: {e}",
        )
        raise

    errors = summary.get("errors") or []
    # Adapters mais antigos (ex.: Bitfin v2.0.0) nao incluem a chave "ok"
    # explicita no summary — apenas a lista de erros. Derivar de errors
    # quando ausente. Adapters que setam "ok" explicito (QiTech) tem
    # precedencia (ok=True com errors=[]; ok=False com errors=[] tambem
    # respeitado).
    ok = bool(summary.get("ok", not errors))
    error_msg = None if ok else "; ".join(str(e) for e in errors[:3])
    await _mark_endpoint_sync_finished(
        tenant_id,
        source_type,
        environment,
        endpoint_name,
        row.unidade_administrativa_id,
        ok=ok,
        error_msg=error_msg,
    )
    return summary
