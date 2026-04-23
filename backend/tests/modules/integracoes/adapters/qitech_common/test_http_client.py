"""httpx client auto-signs outbound QiTech requests."""

from __future__ import annotations

import hashlib
import json

import httpx
import jwt
import pytest

from app.modules.integracoes.adapters._qitech_common.http_client import (
    build_async_client,
)
from tests.modules.integracoes.adapters.qitech_common._fixtures import (
    API_CLIENT_KEY,
    PRIVATE_PEM_P521,
    PUBLIC_PEM_P521,
)


def _decode(token: str) -> dict:
    return jwt.decode(token, PUBLIC_PEM_P521, algorithms=["ES512"])


@pytest.mark.asyncio
async def test_post_request_carries_es512_jwt_over_body() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["content"] = request.content
        return httpx.Response(200, json={"ok": True})

    async with build_async_client(
        base_url="https://api.qitech.test",
        api_client_key=API_CLIENT_KEY,
        private_key_pem=PRIVATE_PEM_P521,
        transport=httpx.MockTransport(handler),
    ) as client:
        body = {"foo": "bar", "n": 42}
        resp = await client.post("/endpoint", json=body)

    assert resp.status_code == 200

    auth = captured["headers"]["authorization"]
    assert auth.startswith("Bearer ")
    token = auth.removeprefix("Bearer ")

    claims = _decode(token)
    assert claims["iss"] == API_CLIENT_KEY
    assert claims["sub"] == API_CLIENT_KEY

    # md5 covers the exact bytes httpx put on the wire, canonicalized by us.
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    assert claims["md5"] == hashlib.md5(canonical.encode()).hexdigest()

    assert captured["headers"]["api-client-key"] == API_CLIENT_KEY


@pytest.mark.asyncio
async def test_get_request_signs_empty_body() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"ok": True})

    async with build_async_client(
        base_url="https://api.qitech.test",
        api_client_key=API_CLIENT_KEY,
        private_key_pem=PRIVATE_PEM_P521,
        transport=httpx.MockTransport(handler),
    ) as client:
        await client.get("/status")

    token = captured["headers"]["authorization"].removeprefix("Bearer ")
    claims = _decode(token)
    # md5 of '{}' per QiTech spec when there's no JSON body.
    assert claims["md5"] == hashlib.md5(b"{}").hexdigest()
