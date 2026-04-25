"""httpx AsyncClient factory — injeta `x-api-key: <apiToken>`.

A QiTech/Singulare **nao usa** `Authorization: Bearer` apesar de emitir um
token OAuth-like via `/v2/painel/token/api`. Validado em 2026-04-24 contra
/v2/netreport/report/market/outros-fundos/{data}:

    - Bearer      -> 500 "A solicitacao nao pode ser concluida."
    - x-api-key   -> 200 + payload canonico

O mesmo token de `/painel/token/api` vai literal no header `x-api-key`.

Usa `httpx.Auth` para resolver o token tardiamente (so no envio da request)
e renova automaticamente se a QiTech retornar 401 — o token pode ter sido
invalidado server-side antes do TTL expirar.

Uso (chamador de dominio):

    async with build_async_client(
        tenant_id=tid, environment=Environment.PRODUCTION, config=cfg
    ) as client:
        resp = await client.get("/v2/netreport/report/market/...")

O caller passa path relativo; `base_url` vem do config e e fixado no client.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID

import httpx

from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.auth import (
    get_api_token,
    invalidate_token,
)
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig

_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class _ApiKeyAuth(httpx.Auth):
    """Auth flow assincrono — injeta o apiToken no header `x-api-key`.

    QiTech usa header customizado, nao `Authorization: Bearer`. Detalhes
    na docstring do modulo.

    Retry: se a QiTech devolver 401 (token invalidado antes do TTL), limpa
    o cache e tenta de novo uma vez. Mais que isso vira loop — a falha
    propaga.

    `requires_response_body=False` para nao segurar o corpo do 401 em
    memoria; basta olhar o status code para decidir pelo refresh.
    """

    requires_request_body = False
    requires_response_body = False

    def __init__(
        self,
        *,
        tenant_id: UUID,
        environment: Environment,
        config: QiTechConfig,
        token_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._environment = environment
        self._config = config
        self._token_transport = token_transport

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        token = await get_api_token(
            tenant_id=self._tenant_id,
            environment=self._environment,
            config=self._config,
            transport=self._token_transport,
        )
        request.headers["x-api-key"] = token
        response = yield request

        # Se o token caducou server-side, invalidamos e tentamos de novo
        # uma vez.
        if response.status_code == 401:
            invalidate_token(self._tenant_id, self._environment)
            token = await get_api_token(
                tenant_id=self._tenant_id,
                environment=self._environment,
                config=self._config,
                transport=self._token_transport,
            )
            request.headers["x-api-key"] = token
            yield request


def build_async_client(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    timeout: httpx.Timeout | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    token_transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Cria um AsyncClient autenticado para o par (tenant, environment).

    Args:
        tenant_id: dono das credenciais — usado na chave do cache de token.
        environment: sandbox ou production.
        config: dataclass ja materializada do tenant_source_config.
        timeout: override opcional do timeout padrao (30s total / 10s connect).
        transport: transport das requests de dominio (MockTransport em tests).
        token_transport: transport das requests de auth (pode ser igual a
            transport, ou distinto para cenarios de teste mais finos).

    Returns:
        AsyncClient nao-entrado. O caller controla o ciclo com `async with`.
    """
    return httpx.AsyncClient(
        base_url=config.base_url,
        timeout=timeout or _DEFAULT_TIMEOUT,
        auth=_ApiKeyAuth(
            tenant_id=tenant_id,
            environment=environment,
            config=config,
            token_transport=token_transport or transport,
        ),
        transport=transport,
    )
