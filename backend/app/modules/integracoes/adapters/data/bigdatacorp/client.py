"""Client de alto nivel — funcoes que callers chamam.

Fase 1: apenas `query_pricing()` — chama POST /precos/ com body vazio e
devolve o catalogo completo (gratis no contrato BDC, todos os datasets
habilitados pra credencial).

Fase 3 (futuro): `query_dataset(category, dataset, q, limit, filters)`
para consumo on-demand pelo modulo credito + outros.

Client NAO toca em DB. Pricing_sync e quem grava — separa adapter puro
testavel da logica de persistencia.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.modules.integracoes.adapters.data.bigdatacorp.config import (
    BigDataCorpConfig,
)
from app.modules.integracoes.adapters.data.bigdatacorp.connection import (
    build_async_client,
)
from app.modules.integracoes.adapters.data.bigdatacorp.errors import (
    BigDataCorpAuthError,
    BigDataCorpHttpError,
    BigDataCorpPayloadError,
)
from app.modules.integracoes.adapters.data.bigdatacorp.version import (
    ADAPTER_VERSION,
)


@dataclass(frozen=True)
class PricingResult:
    """Resultado da consulta a /precos/."""

    payload: dict[str, Any]
    status_code: int
    latency_ms: float
    adapter_version: str = ADAPTER_VERSION


# Endpoint pricing — POST sem body para listar TODA a tabela de precos
# (datasets habilitados na conta + escada de precos por dataset).
# Documentacao: https://docs.bigdatacorp.com.br/plataforma/reference/api-de-precos-requisicao
_PRICING_PATH: str = "/precos/"


async def query_pricing(
    *,
    config: BigDataCorpConfig,
    base_url: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> PricingResult:
    """Chama POST /precos/ com body vazio — devolve catalogo completo.

    Body vazio (`{}`) = "me da TUDO que esta credencial pode acessar".
    Body com `{"API": "...", "Datasets": "..."}` faria estimativa pontual
    de preco — caso de uso da Fase 3 (pre-flight check). Aqui nao usamos.

    Args:
        config: credencial decifrada.
        base_url: do `provedor_dados.base_url` da row do BDC.
        transport: MockTransport pra tests.

    Returns:
        `PricingResult` com payload bruto. O parser/diff fica no
        `pricing_sync.py`.

    Raises:
        BigDataCorpAuthError: se o BDC sinalizar auth invalida.
        BigDataCorpHttpError: 4xx/5xx, timeout, DNS.
        BigDataCorpPayloadError: resposta nao-JSON ou nao-dict.
    """
    if not config.has_credentials():
        raise BigDataCorpAuthError(
            "BDC config sem access_token/token_id — nao chama /precos/"
        )

    t0 = time.monotonic()
    async with build_async_client(
        config=config, base_url=base_url, transport=transport
    ) as client:
        try:
            resp = await client.post(_PRICING_PATH, json={})
        except httpx.HTTPError as e:
            raise BigDataCorpHttpError(
                f"falha de rede em {_PRICING_PATH}: {type(e).__name__}({e!r})",
                status_code=None,
                detail=f"{type(e).__name__}: {e!r}",
            ) from e

    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    if resp.status_code == 401 or resp.status_code == 403:
        raise BigDataCorpAuthError(
            f"BDC rejeitou credencial em {_PRICING_PATH} "
            f"(status {resp.status_code}, body[:200]={resp.text[:200]!r})"
        )

    if resp.status_code >= 400:
        raise BigDataCorpHttpError(
            f"BDC devolveu {resp.status_code} em {_PRICING_PATH}",
            status_code=resp.status_code,
            detail=(resp.text[:1000] if resp.text else "<empty body>"),
        )

    try:
        payload = resp.json()
    except ValueError as e:
        raise BigDataCorpPayloadError(
            f"resposta nao-JSON em {_PRICING_PATH}: {resp.text[:500]}"
        ) from e

    if not isinstance(payload, dict):
        raise BigDataCorpPayloadError(
            f"payload de /precos/ inesperado: {type(payload).__name__}"
        )

    return PricingResult(
        payload=payload,
        status_code=resp.status_code,
        latency_ms=latency_ms,
    )
