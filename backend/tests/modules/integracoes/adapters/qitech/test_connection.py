"""httpx client — injeta `x-api-key` via _ApiKeyAuth + refresh em 401.

A QiTech/Singulare autentica via header customizado `x-api-key` (nao
`Authorization: Bearer`), apesar de emitir um token OAuth-like via
`/v2/painel/token/api`. Descoberto em 2026-04-24 contra o endpoint real
de outros-fundos.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.auth import _clear_cache_for_tests
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.connection import build_async_client


@pytest.fixture(autouse=True)
def _reset_cache():
    _clear_cache_for_tests()
    yield
    _clear_cache_for_tests()


def _cfg() -> QiTechConfig:
    return QiTechConfig(
        base_url="https://api.test",
        client_id="u",
        client_secret="p",
        token_ttl_seconds=3600,
        token_refresh_skew_seconds=60,
    )


class _Transport(httpx.MockTransport):
    """Transport que serve (a) /v2/painel/token/api com tokens sequenciais
    e (b) qualquer outro path com 200 + eco dos headers.

    Permite assertar que o Authorization veio montado no request de dominio.
    """

    def __init__(self, tokens: list[str], domain_status_first: int = 200) -> None:
        self.tokens_iter = iter(tokens)
        self.token_calls = 0
        self.domain_calls: list[httpx.Request] = []
        self._domain_status_first = domain_status_first
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/painel/token/api":
            self.token_calls += 1
            try:
                tok = next(self.tokens_iter)
            except StopIteration:
                tok = "EXHAUSTED"
            return httpx.Response(200, json={"apiToken": tok})

        self.domain_calls.append(request)
        # Primeiro request de dominio pode retornar 401 para testar refresh.
        status = (
            self._domain_status_first if len(self.domain_calls) == 1 else 200
        )
        return httpx.Response(
            status,
            json={
                "x_api_key": request.headers.get("x-api-key"),
                "authorization": request.headers.get("Authorization"),
            },
        )


@pytest.mark.asyncio
async def test_injects_api_key_on_domain_request() -> None:
    transport = _Transport(tokens=["TOKEN-A"])
    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=transport,
    ) as client:
        resp = await client.get("/custody/whatever")

    assert resp.status_code == 200
    body = resp.json()
    assert body["x_api_key"] == "TOKEN-A"
    # Regressao: garante que NAO mandamos Bearer por acidente (QiTech rejeita
    # com 500 generico, mais dificil de debugar que 401 de auth quebrada).
    assert body["authorization"] is None
    assert transport.token_calls == 1


@pytest.mark.asyncio
async def test_refreshes_token_on_401_and_retries() -> None:
    transport = _Transport(
        tokens=["EXPIRED", "FRESH"], domain_status_first=401
    )
    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=transport,
    ) as client:
        resp = await client.get("/custody/anything")

    # Dois requests de dominio: o primeiro retorna 401, o segundo 200.
    assert len(transport.domain_calls) == 2
    assert resp.status_code == 200
    assert resp.json()["x_api_key"] == "FRESH"
    # Dois fetches de token — o inicial + refresh.
    assert transport.token_calls == 2


@pytest.mark.asyncio
async def test_reuses_token_across_sequential_requests() -> None:
    transport = _Transport(tokens=["SINGLE"])
    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=transport,
    ) as client:
        await client.get("/a")
        await client.get("/b")
        await client.get("/c")

    assert transport.token_calls == 1
    assert len(transport.domain_calls) == 3
