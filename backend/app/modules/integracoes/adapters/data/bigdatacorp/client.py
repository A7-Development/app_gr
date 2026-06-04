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


@dataclass(frozen=True)
class EntityQueryResult:
    """Resultado de uma consulta on-demand de entidade (ex.: POST /empresas).

    `payload` e o envelope BDC cru (`Result`, `QueryId`, `Status`, ...). O
    parse/mapper fica fora do client (camada bronze + mapper) — aqui so
    devolvemos o JSON bruto + metadados da chamada.
    """

    payload: dict[str, Any]
    status_code: int
    latency_ms: float
    adapter_version: str = ADAPTER_VERSION


# Endpoint pricing — POST sem body para listar TODA a tabela de precos
# (datasets habilitados na conta + escada de precos por dataset).
# Documentacao: https://docs.bigdatacorp.com.br/plataforma/reference/api-de-precos-requisicao
_PRICING_PATH: str = "/precos/"

# Endpoint de consulta de empresas (PJ). Body documentado:
#   {"Datasets": "basic_data", "q": "doc{<14 digitos>}", "Limit": 1}
# As chaves no `q` sao LITERAIS — a sintaxe de matchkey do BDC e `doc{...}`
# (o MatchKeys do retorno ecoa `doc{...07}`).
# Documentacao: https://docs.bigdatacorp.com.br/plataforma/reference/empresas-dados-cadastrais-basicos
_EMPRESAS_PATH: str = "/empresas"


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


def _build_matchkey_doc(doc: str) -> str:
    """Monta o matchkey `doc{<digitos>}` da query language do BDC.

    Aceita CNPJ/CPF mascarado ou nao — extrai so digitos. As chaves sao
    literais na sintaxe do vendor (nao sao placeholder de template).
    """
    digits = "".join(ch for ch in doc if ch.isdigit())
    return f"doc{{{digits}}}"


async def query_entity(
    *,
    config: BigDataCorpConfig,
    base_url: str,
    doc: str,
    datasets: str,
    limit: int = 1,
    transport: httpx.AsyncBaseTransport | None = None,
) -> EntityQueryResult:
    """Chama POST /empresas com `q=doc{<cnpj>}` — consulta on-demand PJ.

    Diferente de `query_pricing` (gratis), CADA chamada aqui e PAGA pelo
    BDC conforme a faixa do dataset. Caller decide quando chamar (gate
    barato antes, guard de orcamento na Fase de tool).

    Args:
        config: credencial decifrada (AccessToken/TokenId vao no header).
        base_url: de `provedor_dados.base_url` (ex.: "https://plataforma.bigdatacorp.com.br").
        doc: CNPJ (mascarado ou so digitos) — vira matchkey `doc{...}`.
        datasets: nome(s) tecnico(s) do dataset (ex.: "basic_data"). Vai
            literal no campo `Datasets` do body.
        limit: teto de candidatos retornados (default 1 — consulta por CNPJ
            exato devolve no maximo 1).
        transport: MockTransport pra tests.

    Returns:
        `EntityQueryResult` com o envelope BDC cru. `Result: []` = "sem
        dados" (CNPJ nao encontrado) — caller trata como ausencia, nao erro.

    Raises:
        BigDataCorpAuthError: credencial vazia ou recusada (401/403).
        BigDataCorpHttpError: 4xx/5xx, timeout, DNS.
        BigDataCorpPayloadError: resposta nao-JSON ou nao-dict.
    """
    if not config.has_credentials():
        raise BigDataCorpAuthError(
            "BDC config sem access_token/token_id — nao chama /empresas"
        )

    body = {
        "Datasets": datasets,
        "q": _build_matchkey_doc(doc),
        "Limit": limit,
    }

    t0 = time.monotonic()
    async with build_async_client(
        config=config, base_url=base_url, transport=transport
    ) as client:
        try:
            resp = await client.post(_EMPRESAS_PATH, json=body)
        except httpx.HTTPError as e:
            raise BigDataCorpHttpError(
                f"falha de rede em {_EMPRESAS_PATH}: {type(e).__name__}({e!r})",
                status_code=None,
                detail=f"{type(e).__name__}: {e!r}",
            ) from e

    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    if resp.status_code in (401, 403):
        raise BigDataCorpAuthError(
            f"BDC rejeitou credencial em {_EMPRESAS_PATH} "
            f"(status {resp.status_code}, body[:200]={resp.text[:200]!r})"
        )

    if resp.status_code >= 400:
        raise BigDataCorpHttpError(
            f"BDC devolveu {resp.status_code} em {_EMPRESAS_PATH}",
            status_code=resp.status_code,
            detail=(resp.text[:1000] if resp.text else "<empty body>"),
        )

    try:
        payload = resp.json()
    except ValueError as e:
        raise BigDataCorpPayloadError(
            f"resposta nao-JSON em {_EMPRESAS_PATH}: {resp.text[:500]}"
        ) from e

    if not isinstance(payload, dict):
        raise BigDataCorpPayloadError(
            f"payload de {_EMPRESAS_PATH} inesperado: {type(payload).__name__}"
        )

    return EntityQueryResult(
        payload=payload,
        status_code=resp.status_code,
        latency_ms=latency_ms,
    )
