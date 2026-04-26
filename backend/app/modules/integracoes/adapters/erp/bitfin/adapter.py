"""Interface entre sync_runner e o Bitfin.

Exposa duas funcoes async que aceitam `config_dict` (ja decifrado) e retornam
dicts JSON-serializaveis. O sync_runner registra ponteiros para essas funcoes
— nao conhece `BitfinConfig` nem pyodbc.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.modules.integracoes.adapters.erp.bitfin.connection import ping as _conn_ping
from app.modules.integracoes.adapters.erp.bitfin.etl import sync_all
from app.modules.integracoes.adapters.erp.bitfin.version import ADAPTER_VERSION


async def adapter_ping(config_dict: dict, **_: Any) -> dict[str, Any]:
    """Abre conexao MSSQL e executa `SELECT DB_NAME(), @@VERSION`.

    Retorna `{ok, latency_ms, detail}`. Nunca levanta — erros viram `ok=False`
    com `detail` contendo classe + mensagem.

    Aceita kwargs extras (tenant_id, environment) por compatibilidade com
    adapters que precisam de contexto por tenant — Bitfin nao usa.
    """
    config = BitfinConfig.from_dict(config_dict)
    t0 = time.monotonic()
    try:
        info = await asyncio.to_thread(_conn_ping, config, config.database_bitfin)
    except Exception as e:
        return {
            "ok": False,
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "detail": f"{type(e).__name__}: {e}",
            "adapter_version": ADAPTER_VERSION,
        }
    return {
        "ok": True,
        "latency_ms": round((time.monotonic() - t0) * 1000, 1),
        "detail": info,
        "adapter_version": ADAPTER_VERSION,
    }


async def adapter_sync(
    tenant_id: UUID,
    config_dict: dict,
    since: date | None = None,
    *,
    triggered_by: str = "system:scheduler",
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """Entrypoint unificado de sync. Decifra config, roda pipeline completa.

    `unidade_administrativa_id` aceito por compatibilidade com sync_runner
    multi-UA, mas o ETL Bitfin atual filtra por CNPJ (no proprio config) e
    nao consome UA. Quando o adapter Bitfin evoluir pra escopar canonico
    por UA, passar adiante.
    """
    _ = unidade_administrativa_id
    config = BitfinConfig.from_dict(config_dict)
    return await sync_all(tenant_id, config, since=since, triggered_by=triggered_by)
