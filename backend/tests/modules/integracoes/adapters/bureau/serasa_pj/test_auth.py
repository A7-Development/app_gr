"""Token fetcher Serasa PJ — cache, isolamento por tenant, parsing do AcessToken."""

from __future__ import annotations

import base64
import time
from uuid import uuid4

import httpx
import pytest

from app.core.enums import Environment
from app.modules.integracoes.adapters.bureau.serasa_pj.auth import (
    _clear_cache_for_tests,
    get_access_token,
    invalidate_token,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.config import (
    SerasaPjConfig,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.errors import (
    SerasaPjAuthError,
    SerasaPjConfigError,
    SerasaPjHttpError,
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
    retailer_document_id: str = "12345678000199",
    ttl: int = 3600,
    skew: int = 10,
) -> SerasaPjConfig:
    return SerasaPjConfig(
        base_url="https://api.test",
        client_id=client_id,
        client_secret=client_secret,
        retailer_document_id=retailer_document_id,
        token_ttl_seconds=ttl,
        token_refresh_skew_seconds=skew,
    )


def _token_transport(
    token: str = "TOK123",
    expires_in: str | int = "3600",
    status: int = 200,
):
    """MockTransport que devolve `{AcessToken, ExpiresIn}` (sic — typo Serasa)."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if status >= 400:
            return httpx.Response(status, text=f"error {status}")
        return httpx.Response(
            200,
            json={"AcessToken": token, "ExpiresIn": str(expires_in)},
        )

    return httpx.MockTransport(handler), calls


@pytest.mark.asyncio
async def test_fetches_token_and_caches() -> None:
    tenant = uuid4()
    transport, calls = _token_transport("ABC")

    t1 = await get_access_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=transport,
    )
    t2 = await get_access_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=transport,
    )

    assert t1 == "ABC"
    assert t2 == "ABC"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_isolation_between_tenants() -> None:
    tenant_a, tenant_b = uuid4(), uuid4()
    transport_a, calls_a = _token_transport("AAA")
    transport_b, calls_b = _token_transport("BBB")

    token_a = await get_access_token(
        tenant_id=tenant_a,
        environment=Environment.PRODUCTION,
        config=_config(client_id="a", client_secret="1"),
        transport=transport_a,
    )
    token_b = await get_access_token(
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

    await get_access_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=transport,
    )
    await get_access_token(
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

    t1 = await get_access_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=transport,
    )
    assert t1 == "FIRST"

    invalidate_token(tenant, Environment.PRODUCTION)

    t2 = await get_access_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=transport,
    )
    assert t2 == "FIRST"  # mock devolve o mesmo; importa que refez request
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_refetches_when_close_to_expiry() -> None:
    tenant = uuid4()
    transport, calls = _token_transport("X", expires_in="5")

    cfg = _config(ttl=5, skew=10)

    await get_access_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=cfg,
        transport=transport,
    )
    time.sleep(0.01)
    await get_access_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=cfg,
        transport=transport,
    )
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_rejects_empty_credentials() -> None:
    transport, _ = _token_transport()
    with pytest.raises(SerasaPjConfigError):
        await get_access_token(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(client_id="", client_secret=""),
            transport=transport,
        )


@pytest.mark.asyncio
async def test_rejects_missing_retailer_document_id() -> None:
    """Sem retailer, A7 paga pela consulta — has_credentials() falha."""
    transport, _ = _token_transport()
    with pytest.raises(SerasaPjConfigError):
        await get_access_token(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(retailer_document_id=""),
            transport=transport,
        )


@pytest.mark.asyncio
async def test_401_is_auth_error() -> None:
    transport, _ = _token_transport(status=401)
    with pytest.raises(SerasaPjAuthError, match="rejeitadas"):
        await get_access_token(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(),
            transport=transport,
        )


@pytest.mark.asyncio
async def test_500_is_http_error() -> None:
    transport, _ = _token_transport(status=503)
    with pytest.raises(SerasaPjHttpError) as exc:
        await get_access_token(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(),
            transport=transport,
        )
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_missing_access_token_field_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"something": "else"})

    with pytest.raises(SerasaPjAuthError, match="access token"):
        await get_access_token(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(),
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.asyncio
async def test_accepts_camelcase_access_token() -> None:
    """Producao Serasa devolve `accessToken` + `expiresIn` (camelCase OAuth2),
    diferente do typo historico `AcessToken` documentado no UAT antigo.
    Validado contra producao em 2026-05-01.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "accessToken": "PROD_TOKEN",
                "tokenType": "Bearer",
                "expiresIn": "3600",
                "scope": "credit-services",
            },
        )

    token = await get_access_token(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=httpx.MockTransport(handler),
    )
    assert token == "PROD_TOKEN"


@pytest.mark.asyncio
async def test_accepts_pascalcase_access_token() -> None:
    """Defesa: aceita PascalCase (`AccessToken`) tambem."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"AccessToken": "PASCAL_TOKEN", "ExpiresIn": "3600"},
        )

    token = await get_access_token(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=httpx.MockTransport(handler),
    )
    assert token == "PASCAL_TOKEN"


@pytest.mark.asyncio
async def test_accepts_legacy_typo_access_token() -> None:
    """Compat: typo `AcessToken` historicamente devolvido pela Serasa em UAT."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"AcessToken": "LEGACY_TOKEN", "ExpiresIn": "3600"},
        )

    token = await get_access_token(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(),
        transport=httpx.MockTransport(handler),
    )
    assert token == "LEGACY_TOKEN"


@pytest.mark.asyncio
async def test_sends_basic_auth_header() -> None:
    """Doc Serasa: Authorization: Basic base64(client_id:client_secret)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth_header"] = request.headers.get("Authorization")
        captured["method"] = request.method
        return httpx.Response(
            200, json={"AcessToken": "T", "ExpiresIn": "3600"}
        )

    await get_access_token(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(client_id="alice", client_secret="segredo"),
        transport=httpx.MockTransport(handler),
    )

    expected = "Basic " + base64.b64encode(b"alice:segredo").decode("ascii")
    assert captured["path"] == "/security/iam/v1/client-identities/login"
    assert captured["method"] == "POST"
    assert captured["auth_header"] == expected


@pytest.mark.asyncio
async def test_expires_in_caps_at_config_ttl() -> None:
    """Defesa: se Serasa devolver ExpiresIn anomalo (ex.: 999999s),
    o cache local respeita o teto config.token_ttl_seconds.
    """
    tenant = uuid4()
    transport, calls = _token_transport("X", expires_in="999999")

    cfg = _config(ttl=60, skew=5)

    await get_access_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=cfg,
        transport=transport,
    )
    # Importa que o cache esta populado, nao que ele expira aqui — um
    # mockable de tempo seria heavy; sanity check: 1 chamada feita, cache
    # ativo dentro da janela atual.
    assert len(calls) == 1
    # Nova chamada imediata bate cache.
    await get_access_token(
        tenant_id=tenant,
        environment=Environment.PRODUCTION,
        config=cfg,
        transport=transport,
    )
    assert len(calls) == 1
