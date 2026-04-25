"""Interface entre sync_runner e o adapter QiTech.

Mesmo contrato do Bitfin: duas funcoes async recebendo `config_dict` ja
decifrado + `tenant_id` (o `environment` deveria entrar aqui via kwarg
mas mantemos assinatura compativel — `Environment.PRODUCTION` como default
ate o sync_runner repassar o campo).

`adapter_ping` = sanity check: tenta obter um token. Nao pinga nenhum
endpoint de dominio porque, neste momento, so conhecemos o endpoint de
auth. Quando mais endpoints entrarem (custodia, etc.), o ping pode evoluir
para `GET /health` ou similar.

`adapter_sync` = orquestracao real (delegada a `etl.sync_all`): chama o
pipeline registrado de endpoints + grava `decision_log`. O detalhe da
camada raw->canonico fica em `etl.py` (CLAUDE.md secao 13.2).
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any
from uuid import UUID

from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.auth import get_api_token
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechAdapterError
from app.modules.integracoes.adapters.admin.qitech.etl import sync_all
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION


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
) -> dict[str, Any]:
    """Tenta obter um token de API. `ok=True` se o QiTech retornou token.

    Args:
        config_dict: `tenant_source_config.config` decifrado.
        tenant_id: obrigatorio para chavear o cache de token. `None` usa
            um UUID sentinela ("no-tenant") e nunca persiste no cache —
            util so em scripts ad-hoc.
        environment: padrao `production`.

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
            tenant_id=tid, environment=environment, config=config
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
        },
    )


async def adapter_sync(
    tenant_id: UUID,
    config_dict: dict,
    since: date | None = None,
    *,
    triggered_by: str = "system:scheduler",
    environment: Environment = Environment.PRODUCTION,
) -> dict[str, Any]:
    """Orquestra sync completo: auth + endpoints + raw + canonico + decision_log.

    Delegacao a `etl.sync_all` (CLAUDE.md secao 13.2). O `since` aqui
    representa **data alvo** (nao "desde quando incremental") — a API QiTech
    e por dia exato. Se None, `etl.sync_all` resolve para D-1 UTC.

    Auth e validado uma vez antes do pipeline rodar. Falha de auth aborta
    todo o ciclo; falha em endpoint individual nao aborta os demais.
    """
    config = QiTechConfig.from_dict(config_dict)
    t0 = time.monotonic()

    # Sanity check de auth — se falhar, nao adianta tentar endpoints.
    try:
        await get_api_token(
            tenant_id=tenant_id,
            environment=environment,
            config=config,
        )
    except QiTechAdapterError as e:
        return {
            "ok": False,
            "adapter_version": ADAPTER_VERSION,
            "tenant_id": str(tenant_id),
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
    )
