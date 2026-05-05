"""httpx AsyncClient factory — injeta AccessToken + TokenId em toda request.

Diferente do Serasa (Bearer + retry no 401), o BDC usa headers fixos sem
TTL. Toda chamada manda os mesmos dois headers; rejeicao de auth nao tem
retry automatico (se token foi revogado, mantenedor rotaciona credencial).
"""

from __future__ import annotations

import httpx

from app.modules.integracoes.adapters.data.bigdatacorp.config import (
    BigDataCorpConfig,
)

_DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def build_async_client(
    *,
    config: BigDataCorpConfig,
    base_url: str,
    timeout: httpx.Timeout | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Cria um AsyncClient autenticado.

    Args:
        config: credencial materializada do envelope decifrado.
        base_url: vem de `provedor_dados.base_url` (ex.: "https://plataforma.bigdatacorp.com.br").
        timeout: override opcional do timeout padrao (60s total / 10s connect).
        transport: MockTransport em tests.

    Returns:
        AsyncClient nao-entrado. Caller controla com `async with`.
    """
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout or _DEFAULT_TIMEOUT,
        headers={
            "AccessToken": config.access_token,
            "TokenId": config.token_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        transport=transport,
    )
