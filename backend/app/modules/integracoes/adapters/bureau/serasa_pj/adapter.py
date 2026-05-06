"""Interface entre sync_runner / routers e o adapter Serasa PJ.

Mesmo contrato dos adapters de sync (Bitfin, QiTech), com duas diferencas:

1. **`adapter_ping` autentica de verdade.** Tenta obter Access Token; se a
   Serasa devolver token, a credencial + retailer_document_id estao OK e o
   tenant pode disparar consultas. Nao chama nenhum endpoint de relatorio
   (cada chamada custa) — sanity check de rede + credencial e suficiente.

2. **`adapter_sync` e stub explicativo.** Bureau e query sob demanda, nao
   sync periodico. Retorna dict com explicacao em `errors` para o operador
   entender que esta fonte nao tem botao "Sync agora" — consultas sao
   disparadas pelo workflow do credito (ou outros futuros consumidores).

A assinatura aceita `unidade_administrativa_id` por compat de interface
com QiTech, mas IGNORA o valor — Serasa usa 1 credencial por tenant.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any
from uuid import UUID

from app.core.enums import Environment
from app.modules.integracoes.adapters.bureau.serasa_pj.auth import (
    get_access_token,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.config import (
    SerasaPjConfig,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.errors import (
    SerasaPjAdapterError,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.version import (
    ADAPTER_VERSION,
)


def _shape_ok(*, t0: float, detail: Any) -> dict[str, Any]:
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
    """Tenta obter um Access Token. `ok=True` se a Serasa emitiu token.

    Args:
        config_dict: `tenant_source_config.config` decifrado.
        tenant_id: obrigatorio para chavear o cache de token. `None` usa
            UUID sentinela — util so em scripts ad-hoc.
        environment: producao por padrao.
        unidade_administrativa_id: ignorado (compat de interface). Serasa
            usa 1 credencial por tenant.

    Returns:
        Dict no formato `{ok, latency_ms, detail, adapter_version}`. Nunca
        levanta.
    """
    config = SerasaPjConfig.from_dict(config_dict)
    t0 = time.monotonic()

    tid = tenant_id or UUID(int=0)

    try:
        token = await get_access_token(
            tenant_id=tid,
            environment=environment,
            config=config,
        )
    except SerasaPjAdapterError as e:
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
            "retailer_document_id_set": bool(config.retailer_document_id),
            "score_model_pj": config.score_model_pj,
            "default_report_type": config.default_report_type,
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
    """Stub — bureau adapters nao sincronizam.

    Retorna summary com `errors` explicando que a fonte e query sob demanda.
    Operador que clicou em "Sync agora" no /admin/integracoes ve a mensagem
    e entende que precisa disparar consulta especifica via workflow.

    Nao levanta (sync_runner espera dict).
    """
    return {
        "ok": False,
        "adapter_version": ADAPTER_VERSION,
        "tenant_id": str(tenant_id),
        "environment": environment.value,
        "triggered_by": triggered_by,
        "since": since.isoformat() if since else None,
        "elapsed_seconds": 0.0,
        "errors": [
            "Serasa PJ e bureau de consulta sob demanda — nao tem sync periodico. "
            "Dispare consulta de CNPJ via workflow do modulo credito.",
        ],
        "rows_ingested": 0,
        "steps": [],
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
    """Stub per-endpoint — Serasa nao tem catalogo de endpoints (consulta
    sob demanda). Adicionado para manter interface uniforme com QiTech/Bitfin.

    O dispatcher nunca devera chamar esta funcao porque
    `endpoint_catalog(BUREAU_SERASA_PJ)` retorna lista vazia — sem linha em
    `tenant_source_endpoint_config` que dispatcher pudesse iterar. Mas se
    chamado (ex.: API admin manual), retorna o mesmo stub explicativo.
    """
    summary = await adapter_sync(
        tenant_id,
        config_dict,
        since=since,
        triggered_by=triggered_by,
        environment=environment,
        unidade_administrativa_id=unidade_administrativa_id,
    )
    summary["endpoint_name"] = endpoint_name
    return summary
