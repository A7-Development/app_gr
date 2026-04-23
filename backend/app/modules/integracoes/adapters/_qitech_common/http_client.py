"""httpx AsyncClient factory that auto-signs QiTech requests.

Each outbound request carries a freshly-minted ES512 JWT computed over the
request body — so we intercept every call via an `httpx.Auth` flow. This keeps
BU adapters free of signing boilerplate: they just call `client.post("/endpoint", json=...)`.

Usage (BU adapter):

    from app.modules.integracoes.adapters._qitech_common import build_async_client

    async with build_async_client(
        base_url="https://api.qitech.com.br",
        api_client_key=config.client_key,
        private_key_pem=config.client_private_key_pem,
    ) as client:
        resp = await client.post("/custody/some-endpoint", json=body)

Signing contract is defined in `signer.sign_request_jwt` — this module is a
thin plumbing layer; the actual crypto lives there.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import httpx

from app.modules.integracoes.adapters._qitech_common.signer import (
    sign_request_jwt,
)

_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class _QiTechAuth(httpx.Auth):
    """httpx Auth flow that attaches a fresh ES512 JWT to every request.

    `requires_request_body=True` is critical — without it, httpx may hand us
    the request BEFORE body serialization, and the md5 claim ends up computed
    over the wrong bytes.
    """

    requires_request_body = True

    def __init__(self, *, api_client_key: str, private_key_pem: str) -> None:
        self._api_client_key = api_client_key
        self._private_key_pem = private_key_pem

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        body_dict = _extract_json_body(request)
        token = sign_request_jwt(
            api_client_key=self._api_client_key,
            private_key_pem=self._private_key_pem,
            body=body_dict,
        )
        request.headers["Authorization"] = f"Bearer {token}"
        request.headers["API-CLIENT-KEY"] = self._api_client_key
        yield request


def _extract_json_body(request: httpx.Request) -> dict[str, Any] | None:
    """Recover the JSON dict from a httpx.Request, if any.

    QiTech expects the md5 claim over the JSON body the server will see.
    We re-decode the bytes rather than remembering the original dict because
    httpx is authoritative over the wire format.
    """
    if not request.content:
        return None
    # Only JSON bodies contribute to the md5 claim. Form/multipart/raw bytes
    # are untouched — the server signs those differently (out of scope).
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return None
    import json

    try:
        decoded = json.loads(request.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def build_async_client(
    *,
    base_url: str,
    api_client_key: str,
    private_key_pem: str,
    timeout: httpx.Timeout | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Create an httpx AsyncClient that auto-signs requests for a tenant.

    Args:
        base_url: QiTech base URL (per-BU or per-environment).
        api_client_key: tenant UUID na QiTech.
        private_key_pem: PEM ECDSA P-521 do tenant.
        timeout: optional httpx.Timeout override (default: 30s total, 10s connect).
        transport: optional AsyncBaseTransport for tests (MockTransport).

    Returns:
        An un-entered AsyncClient. Caller owns the lifecycle (`async with`).
    """
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout or _DEFAULT_TIMEOUT,
        auth=_QiTechAuth(
            api_client_key=api_client_key,
            private_key_pem=private_key_pem,
        ),
        transport=transport,
    )
