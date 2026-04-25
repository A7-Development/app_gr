"""Token fetcher — cache, isolamento multi-tenant, tratamento de erro."""

from __future__ import annotations

import base64
import time
from uuid import uuid4

import httpx
import pytest

from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.auth import (
    _clear_cache_for_tests,
    get_api_token,
    invalidate_token,
)
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.errors import (
    QiTechAuthError,
    QiTechHttpError,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    _clear_cache_for_tests()
    yield
    _clear_cache_for_tests()


def _config(
    *,
    client_id: str = "u",
    client_secret: str = "p",
    ttl: int = 3600,
) -> QiTechConfig:
    return QiTechConfig(
        base_url="https://api.test",
        client_id=client_id,
        client_secret=client_secret,
        token_ttl_seconds=ttl,
        token_refresh_skew_seconds=10,
    )


def _token_transport(token: str = "TOK123", status: int = 200):
    """MockTransport que sempre devolve `{apiToken: ...}` no status dado."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if status >= 400:
            return httpx.Response(status, text=f"error {status}")
        return httpx.Response(200, json={"apiToken": token})

    return httpx.MockTransport(handler), calls


@pytest.mark.asyncio
async def test_fetches_token_and_caches() -> None:
    tenant = uuid4()
    transport, calls = _token_transport("ABC")

    t1 = await get_api_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=transport,
    )
    t2 = await get_api_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=transport,
    )

    assert t1 == "ABC"
    assert t2 == "ABC"
    # cache bateu no segundo — so 1 request de rede.
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_isolation_between_tenants() -> None:
    tenant_a, tenant_b = uuid4(), uuid4()
    transport_a, calls_a = _token_transport("AAA")
    transport_b, calls_b = _token_transport("BBB")

    token_a = await get_api_token(
        tenant_id=tenant_a,
        environment=Environment.PRODUCTION,
        config=_config(client_id="a", client_secret="1"),
        transport=transport_a,
    )
    token_b = await get_api_token(
        tenant_id=tenant_b,
        environment=Environment.PRODUCTION,
        config=_config(client_id="b", client_secret="2"),
        transport=transport_b,
    )

    assert token_a == "AAA"
    assert token_b == "BBB"
    assert len(calls_a) == 1
    assert len(calls_b) == 1


@pytest.mark.asyncio
async def test_sandbox_and_production_have_separate_caches() -> None:
    tenant = uuid4()
    transport, calls = _token_transport("SAMEKEY")

    await get_api_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=transport,
    )
    await get_api_token(
        tenant_id=tenant,
        environment=Environment.SANDBOX,
        config=_config(),
        transport=transport,
    )

    # Mesmo tenant, ambientes distintos — dois fetches.
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_refetches_after_invalidate() -> None:
    tenant = uuid4()
    transport, calls = _token_transport("FIRST")

    t1 = await get_api_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=transport,
    )
    assert t1 == "FIRST"

    invalidate_token(tenant, Environment.PRODUCTION)

    t2 = await get_api_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=transport,
    )
    assert t2 == "FIRST"  # o mock devolve o mesmo; o ponto e que refez a request
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_refetches_when_close_to_expiry() -> None:
    tenant = uuid4()
    transport, calls = _token_transport("X")

    cfg = QiTechConfig(
        base_url="https://api.test",
        client_id="u",
        client_secret="p",
        # TTL muito curto + skew alto = cache sempre considera "quase expirado".
        token_ttl_seconds=5,
        token_refresh_skew_seconds=10,
    )

    await get_api_token(
        tenant_id=tenant, environment=Environment.PRODUCTION, config=cfg, transport=transport
    )
    # tempo nao passou, mas skew >= TTL faz o proximo fetch bater novamente.
    time.sleep(0.01)
    await get_api_token(
        tenant_id=tenant, environment=Environment.PRODUCTION, config=cfg, transport=transport
    )
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_rejects_empty_credentials() -> None:
    transport, _ = _token_transport()
    with pytest.raises(QiTechAuthError, match="client_id/client_secret"):
        await get_api_token(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(client_id="", client_secret=""),
            transport=transport,
        )


@pytest.mark.asyncio
async def test_rejects_partial_credentials() -> None:
    # Ter so client_id sem secret e tao invalido quanto ter ambos vazios.
    transport, _ = _token_transport()
    with pytest.raises(QiTechAuthError, match="client_id/client_secret"):
        await get_api_token(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(client_id="only-id", client_secret=""),
            transport=transport,
        )


@pytest.mark.asyncio
async def test_401_is_auth_error() -> None:
    transport, _ = _token_transport(status=401)
    with pytest.raises(QiTechAuthError, match="rejeitadas"):
        await get_api_token(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(),
            transport=transport,
        )


@pytest.mark.asyncio
async def test_500_is_http_error() -> None:
    transport, _ = _token_transport(status=503)
    with pytest.raises(QiTechHttpError) as exc:
        await get_api_token(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(),
            transport=transport,
        )
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_missing_api_token_field_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"something": "else"})

    with pytest.raises(QiTechAuthError, match="apiToken"):
        await get_api_token(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(),
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.asyncio
async def test_sends_basic_auth_header() -> None:
    """Doc Singulare/QiTech: Authorization: Basic base64(client_id:client_secret)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth_header"] = request.headers.get("Authorization")
        captured["body_len"] = len(request.content)
        return httpx.Response(200, json={"apiToken": "T"})

    await get_api_token(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(client_id="alice", client_secret="segredo"),
        transport=httpx.MockTransport(handler),
    )

    expected = "Basic " + base64.b64encode(b"alice:segredo").decode("ascii")
    assert captured["path"] == "/v2/painel/token/api"
    assert captured["auth_header"] == expected
    # Basic auth nao carrega body; httpx pode mandar 0 bytes.
    assert captured["body_len"] == 0
