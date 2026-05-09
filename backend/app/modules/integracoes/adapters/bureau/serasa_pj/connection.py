"""httpx AsyncClient factory — injeta Bearer + X-Retailer-Document-Id.

Diferente do QiTech (que usa header customizado `x-api-key`), a Serasa
exige `Authorization: Bearer <token>` em formato OAuth2 padrao.

O header `X-Retailer-Document-Id` (CNPJ do consultante real) tambem e
injetado em toda chamada — sem ele, consumo cai pra A7 em vez do tenant.
Vem direto do `config.retailer_document_id`.

Auth flow assincrono trata 401 invalidando o cache e reenviando uma vez —
mesmo padrao do QiTech.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID

import httpx

from app.core.enums import Environment
from app.modules.integracoes.adapters.bureau.serasa_pj.auth import (
    get_access_token,
    invalidate_token,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.config import (
    SerasaPjConfig,
)

_DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class _BearerAuthWithRetailer(httpx.Auth):
    """Auth flow assincrono — Bearer + X-Retailer-Document-Id em toda request.

    Retry: se a Serasa devolver 401 (token invalidado antes do TTL), limpa
    o cache e tenta de novo uma vez. Mais que isso vira loop — propaga.
    """

    requires_request_body = False
    requires_response_body = False

    def __init__(
        self,
        *,
        tenant_id: UUID,
        environment: Environment,
        config: SerasaPjConfig,
        token_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._environment = environment
        self._config = config
        self._token_transport = token_transport

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        token = await get_access_token(
            tenant_id=self._tenant_id,
            environment=self._environment,
            config=self._config,
            transport=self._token_transport,
        )
        request.headers["Authorization"] = f"Bearer {token}"
        request.headers["X-Retailer-Document-Id"] = (
            self._config.retailer_document_id
        )
        # WAFs Serasa em prod podem rejeitar silenciosamente requests sem
        # `Accept` explicito (404 com body vazio em vez de 415). Nao causa
        # mal em UAT onde Accept e tolerado.
        request.headers.setdefault("Accept", "application/json")
        response = yield request

        if response.status_code == 401:
            invalidate_token(self._tenant_id, self._environment)
            token = await get_access_token(
                tenant_id=self._tenant_id,
                environment=self._environment,
                config=self._config,
                transport=self._token_transport,
            )
            request.headers["Authorization"] = f"Bearer {token}"
            request.headers["X-Retailer-Document-Id"] = (
                self._config.retailer_document_id
            )
            request.headers.setdefault("Accept", "application/json")
            yield request


def build_async_client(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: SerasaPjConfig,
    timeout: httpx.Timeout | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    token_transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Cria um AsyncClient autenticado para a tupla (tenant, environment).

    Args:
        tenant_id: dono das credenciais — usado na chave do cache de token.
        environment: sandbox/UAT ou production.
        config: dataclass ja materializada do tenant_source_config.
        timeout: override opcional do timeout padrao (60s total / 10s connect).
            Default mais alto que QiTech porque Business Information Report
            tem cold-path de 5-15s tipico.
        transport: transport das requests de dominio (MockTransport em tests).
        token_transport: transport das requests de auth (default = transport).

    Returns:
        AsyncClient nao-entrado. O caller controla o ciclo com `async with`.
    """
    return httpx.AsyncClient(
        base_url=config.base_url,
        timeout=timeout or _DEFAULT_TIMEOUT,
        auth=_BearerAuthWithRetailer(
            tenant_id=tenant_id,
            environment=environment,
            config=config,
            token_transport=token_transport or transport,
        ),
        transport=transport,
    )
