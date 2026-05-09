"""Interface entre sync_runner e o adapter QiTech.

Tres entrypoints:

- `adapter_ping`: sanity check (tenta obter um token).
- `adapter_sync`: ciclo legado — sincroniza TODOS os endpoints (delegado a
  `etl.sync_all`). Mantido para compat com modo legado do dispatcher
  (feature flag INTEGRACOES_USE_ENDPOINT_SCHEDULING=False) ate o cleanup
  final.
- `adapter_sync_endpoint`: novo (2026-05-05) — sincroniza UM endpoint por
  vez, identificado por `endpoint_name` do catalogo declarativo
  (`endpoint_catalog.py`). Usado pelo dispatcher quando flag liga.

`endpoint_name` -> handler dict mapeia o nome canonico para a funcao
existente em `etl.py` (market.*) ou `bank_account_sync.py` (bank_account.*).
Adicionar endpoint = adicionar entrada no catalogo + handler aqui +
snapshot na migration.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech import bank_account_sync
from app.modules.integracoes.adapters.admin.qitech.auth import get_api_token
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.endpoint_catalog import (
    QITECH_ENDPOINTS_BY_NAME,
)
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechAdapterError
from app.modules.integracoes.adapters.admin.qitech.etl import (
    sync_all,
    sync_conta_corrente,
    sync_cpr,
    sync_demonstrativo_caixa,
    sync_mec,
    sync_outros_ativos,
    sync_outros_fundos,
    sync_rentabilidade,
    sync_rf,
    sync_rf_compromissadas,
    sync_tesouraria,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION
from app.shared.audit_log.decision_log import DecisionLog, DecisionType


def _shape_ok(
    *, t0: float, detail: Any
) -> dict[str, Any]:
    return {
        "ok": True,
        "latency_ms": round((time.monotonic() - t0) * 1000, 1),
        "detail": detail,
        "adapter_version": ADAPTER_VERSION,
    }


def _shape_err(*, t0: float, e: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "latency_ms": round((time.monotonic() - t0) * 1000, 1),
        "detail": f"{type(e).__name__}: {e}",
        "adapter_version": ADAPTER_VERSION,
    }


async def adapter_ping(
    config_dict: dict,
    *,
    tenant_id: UUID | None = None,
    environment: Environment = Environment.PRODUCTION,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """Tenta obter um token de API. `ok=True` se o QiTech retornou token.

    Args:
        config_dict: `tenant_source_config.config` decifrado.
        tenant_id: obrigatorio para chavear o cache de token. `None` usa
            um UUID sentinela ("no-tenant") e nunca persiste no cache —
            util so em scripts ad-hoc.
        environment: padrao `production`.
        unidade_administrativa_id: UA dona desta credencial (multi-UA).

    Returns:
        Dict no formato `{ok, latency_ms, detail, adapter_version}`.
        Nunca levanta.
    """
    config = QiTechConfig.from_dict(config_dict)
    t0 = time.monotonic()

    # Se o caller nao forneceu tenant_id (bootstrap CLI, por exemplo),
    # usamos um UUID stub — cache nao contamina tenants reais porque
    # UUID(int=0) nunca coincide com um tenant legitimo.
    tid = tenant_id or UUID(int=0)

    try:
        token = await get_api_token(
            tenant_id=tid,
            environment=environment,
            config=config,
            unidade_administrativa_id=unidade_administrativa_id,
        )
    except QiTechAdapterError as e:
        return _shape_err(t0=t0, e=e)
    except Exception as e:  # defensive — nunca estourar para o UI
        return _shape_err(t0=t0, e=e)

    return _shape_ok(
        t0=t0,
        detail={
            "authenticated": True,
            "token_prefix": f"{token[:8]}...",
            "base_url": config.base_url,
            "environment": environment.value,
            "unidade_administrativa_id": (
                str(unidade_administrativa_id)
                if unidade_administrativa_id
                else None
            ),
        },
    )


async def adapter_sync(
    tenant_id: UUID,
    config_dict: dict,
    since: date | None = None,
    *,
    triggered_by: str = "system:scheduler",
    environment: Environment = Environment.PRODUCTION,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """Orquestra sync completo: auth + endpoints + raw + canonico + decision_log.

    Delegacao a `etl.sync_all` (CLAUDE.md secao 13.2). O `since` aqui
    representa **data alvo** (nao "desde quando incremental") — a API QiTech
    e por dia exato. Se None, `etl.sync_all` resolve para D-1 UTC.

    Auth e validado uma vez antes do pipeline rodar. Falha de auth aborta
    todo o ciclo; falha em endpoint individual nao aborta os demais.

    Multi-UA: `unidade_administrativa_id` chaveia cache de token e e
    propagado pra raw + canonical, garantindo que dados de UA-A nao
    sobrescrevam dados de UA-B no warehouse.
    """
    config = QiTechConfig.from_dict(config_dict)
    t0 = time.monotonic()

    # Sanity check de auth — se falhar, nao adianta tentar endpoints.
    try:
        await get_api_token(
            tenant_id=tenant_id,
            environment=environment,
            config=config,
            unidade_administrativa_id=unidade_administrativa_id,
        )
    except QiTechAdapterError as e:
        return {
            "ok": False,
            "adapter_version": ADAPTER_VERSION,
            "tenant_id": str(tenant_id),
            "unidade_administrativa_id": (
                str(unidade_administrativa_id)
                if unidade_administrativa_id
                else None
            ),
            "environment": environment.value,
            "triggered_by": triggered_by,
            "since": since.isoformat() if since else None,
            "elapsed_seconds": round(time.monotonic() - t0, 2),
            "errors": [f"auth: {type(e).__name__}: {e}"],
            "rows_ingested": 0,
            "steps": [],
        }

    return await sync_all(
        tenant_id,
        config,
        since,
        environment=environment,
        triggered_by=triggered_by,
        unidade_administrativa_id=unidade_administrativa_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# adapter_sync_endpoint — sync de UM endpoint por vez (modo per-endpoint)
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_data_alvo(since: date | None) -> date:
    """Resolve `since` para a data alvo do sync (D-1 default).

    Mesma logica de `etl._resolve_data_posicao` — duplicada aqui pra evitar
    import circular adapter <-> etl, e porque adapter_sync_endpoint nao
    chama mais o sync_all do etl.
    """
    if since is not None:
        return since
    return (datetime.now(UTC) - timedelta(days=1)).date()


def _resolve_data_hoje(since: date | None) -> date:
    """Resolve para hoje (UTC). Usado para bank_account.statement, que e
    intraday — operador quer o extrato do dia atual."""
    if since is not None:
        return since
    return datetime.now(UTC).date()


async def _handler_market(
    *,
    sync_fn: Any,  # callable async
    tenant_id: UUID,
    config: QiTechConfig,
    environment: Environment,
    unidade_administrativa_id: UUID | None,
    since: date | None,
) -> list[dict[str, Any]]:
    """Wrapper para market.* — chama o sync_<tipo> existente em etl.py."""
    data_posicao = _resolve_data_alvo(since)
    step = await sync_fn(
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
        unidade_administrativa_id=unidade_administrativa_id,
    )
    return [step]


async def _handler_bank_balance(
    *,
    tenant_id: UUID,
    config: QiTechConfig,
    environment: Environment,
    unidade_administrativa_id: UUID | None,
    since: date | None,
) -> list[dict[str, Any]]:
    """Wrapper para bank_account.balance — itera todas as contas da UA."""
    if unidade_administrativa_id is None:
        return [_step_error("bank_account.balance", "UA obrigatoria — bank_account requer UA configurada.")]
    data_alvo = _resolve_data_hoje(since)
    return await bank_account_sync.sync_balance_all_accounts(
        tenant_id=tenant_id,
        unidade_administrativa_id=unidade_administrativa_id,
        environment=environment,
        config=config,
        data=data_alvo,
    )


async def _handler_bank_statement(
    *,
    tenant_id: UUID,
    config: QiTechConfig,
    environment: Environment,
    unidade_administrativa_id: UUID | None,
    since: date | None,
) -> list[dict[str, Any]]:
    """Wrapper para bank_account.statement — janela de 1 dia (hoje), todas
    contas da UA. Multi-day backfill via API admin que aceita range explicito."""
    if unidade_administrativa_id is None:
        return [_step_error("bank_account.statement", "UA obrigatoria — bank_account requer UA configurada.")]
    data_alvo = _resolve_data_hoje(since)
    return await bank_account_sync.sync_statement_all_accounts(
        tenant_id=tenant_id,
        unidade_administrativa_id=unidade_administrativa_id,
        environment=environment,
        config=config,
        inicio=data_alvo,
        fim=data_alvo,
    )


def _step_error(name: str, msg: str) -> dict[str, Any]:
    """Step com erro — usado quando handler reprova condicao previa."""
    return {
        "name": name,
        "ok": False,
        "errors": [msg],
        "elapsed_seconds": 0.0,
    }


# Mapping endpoint_name -> handler. Adicionar endpoint = adicionar linha aqui
# + entrada no `endpoint_catalog.py` + snapshot da migration.
_HANDLERS: dict[str, Any] = {
    "market.outros_fundos": lambda **kw: _handler_market(sync_fn=sync_outros_fundos, **kw),
    "market.conta_corrente": lambda **kw: _handler_market(sync_fn=sync_conta_corrente, **kw),
    "market.tesouraria": lambda **kw: _handler_market(sync_fn=sync_tesouraria, **kw),
    "market.outros_ativos": lambda **kw: _handler_market(sync_fn=sync_outros_ativos, **kw),
    "market.demonstrativo_caixa": lambda **kw: _handler_market(sync_fn=sync_demonstrativo_caixa, **kw),
    "market.cpr": lambda **kw: _handler_market(sync_fn=sync_cpr, **kw),
    "market.mec": lambda **kw: _handler_market(sync_fn=sync_mec, **kw),
    "market.rentabilidade": lambda **kw: _handler_market(sync_fn=sync_rentabilidade, **kw),
    "market.rf": lambda **kw: _handler_market(sync_fn=sync_rf, **kw),
    "market.rf_compromissadas": lambda **kw: _handler_market(sync_fn=sync_rf_compromissadas, **kw),
    "bank_account.balance": _handler_bank_balance,
    "bank_account.statement": _handler_bank_statement,
}


async def adapter_sync_endpoint(
    tenant_id: UUID,
    config_dict: dict,
    endpoint_name: str,
    *,
    since: date | None = None,
    triggered_by: str = "system:scheduler",
    environment: Environment = Environment.PRODUCTION,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """Sincroniza UM endpoint da QiTech, identificado por `endpoint_name`.

    Diferenca de `adapter_sync`:
        - `adapter_sync`: itera _PIPELINE inteiro (todos endpoints market).
        - `adapter_sync_endpoint`: chama 1 handler especifico, gerando 1 entry
          em `decision_log` com `endpoint_name` preenchido.

    Auth e validado uma vez antes do handler. Falha de auth aborta a sync.

    Levanta ValueError se `endpoint_name` nao esta no catalogo (caller
    deve validar antes via `endpoint_catalog`). Falhas dentro do handler
    sao capturadas em `errors` (mesmo padrao do sync_all).
    """
    if endpoint_name not in QITECH_ENDPOINTS_BY_NAME:
        raise ValueError(
            f"Endpoint desconhecido para QiTech: {endpoint_name!r}. "
            f"Conhecidos: {sorted(QITECH_ENDPOINTS_BY_NAME.keys())}"
        )

    handler = _HANDLERS.get(endpoint_name)
    if handler is None:
        # Catalogo declara mas handler nao implementado — bug de
        # consistencia. Falha alta para chamar atencao.
        raise RuntimeError(
            f"QiTech: endpoint {endpoint_name!r} no catalogo mas sem handler em _HANDLERS"
        )

    config = QiTechConfig.from_dict(config_dict)
    started_at = datetime.now(UTC)
    t0 = time.monotonic()

    # Auth check uma vez antes do handler.
    try:
        await get_api_token(
            tenant_id=tenant_id,
            environment=environment,
            config=config,
            unidade_administrativa_id=unidade_administrativa_id,
        )
    except QiTechAdapterError as e:
        elapsed = round(time.monotonic() - t0, 2)
        summary: dict[str, Any] = {
            "ok": False,
            "adapter_version": ADAPTER_VERSION,
            "tenant_id": str(tenant_id),
            "unidade_administrativa_id": (
                str(unidade_administrativa_id)
                if unidade_administrativa_id
                else None
            ),
            "environment": environment.value,
            "endpoint_name": endpoint_name,
            "started_at": started_at.isoformat(),
            "elapsed_seconds": elapsed,
            "rows_ingested": 0,
            "steps": [],
            "errors": [f"auth: {type(e).__name__}: {e}"],
            "since": since.isoformat() if since else None,
            "triggered_by": triggered_by,
        }
        await _record_decision_log(
            tenant_id=tenant_id,
            endpoint_name=endpoint_name,
            triggered_by=triggered_by,
            environment=environment,
            since=since,
            summary=summary,
        )
        return summary

    # Handler — captura excecao geral pra nao explodir o tick do dispatcher.
    errors: list[str] = []
    steps: list[dict[str, Any]] = []
    try:
        result = await handler(
            tenant_id=tenant_id,
            config=config,
            environment=environment,
            unidade_administrativa_id=unidade_administrativa_id,
            since=since,
        )
        # Handler pode retornar 1 step (dict) ou lista (multi-account).
        steps = [result] if isinstance(result, dict) else list(result)
        for step in steps:
            for err in step.get("errors") or []:
                errors.append(f"{step.get('name', endpoint_name)}: {err}")
    except Exception as e:
        errors.append(f"{endpoint_name}: {type(e).__name__}: {e}")

    elapsed = round(time.monotonic() - t0, 2)
    rows_total = sum(int(s.get("canonical_rows_upserted") or 0) for s in steps)
    summary = {
        "ok": not errors,
        "adapter_version": ADAPTER_VERSION,
        "tenant_id": str(tenant_id),
        "unidade_administrativa_id": (
            str(unidade_administrativa_id)
            if unidade_administrativa_id
            else None
        ),
        "environment": environment.value,
        "endpoint_name": endpoint_name,
        "started_at": started_at.isoformat(),
        "elapsed_seconds": elapsed,
        "rows_ingested": rows_total,
        "steps": steps,
        "errors": errors,
        "since": since.isoformat() if since else None,
        "triggered_by": triggered_by,
    }

    await _record_decision_log(
        tenant_id=tenant_id,
        endpoint_name=endpoint_name,
        triggered_by=triggered_by,
        environment=environment,
        since=since,
        summary=summary,
    )
    return summary


async def _record_decision_log(
    *,
    tenant_id: UUID,
    endpoint_name: str,
    triggered_by: str,
    environment: Environment,
    since: date | None,
    summary: dict[str, Any],
) -> None:
    """Append-only audit trail (CLAUDE.md §14.2) — entrada por endpoint."""
    errors = summary.get("errors") or []
    async with AsyncSessionLocal() as db:
        db.add(
            DecisionLog(
                tenant_id=tenant_id,
                decision_type=DecisionType.SYNC,
                inputs_ref={
                    "endpoint_name": endpoint_name,
                    "environment": environment.value,
                    "since": since.isoformat() if since else None,
                },
                rule_or_model="qitech_adapter",
                rule_or_model_version=ADAPTER_VERSION,
                endpoint_name=endpoint_name,
                output=summary,
                explanation=(
                    "OK" if not errors else f"{len(errors)} erro(s): {errors}"
                ),
                triggered_by=triggered_by,
            )
        )
        await db.commit()
