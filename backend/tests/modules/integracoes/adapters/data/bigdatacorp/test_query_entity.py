"""query_entity — body, headers, matchkey doc{}, envelope, erros.

Adapter BDC usa POST /empresas com body
`{"Datasets": "...", "q": "doc{<digitos>}", "Limit": N}` e headers fixos
AccessToken/TokenId (sem TTL/refresh).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.modules.integracoes.adapters.data.bigdatacorp.client import query_entity
from app.modules.integracoes.adapters.data.bigdatacorp.config import (
    BigDataCorpConfig,
)
from app.modules.integracoes.adapters.data.bigdatacorp.errors import (
    BigDataCorpAuthError,
    BigDataCorpHttpError,
    BigDataCorpPayloadError,
)

_BASE_URL = "https://plataforma.test"


def _config() -> BigDataCorpConfig:
    return BigDataCorpConfig(access_token="AT", token_id="TID")


class _Transport(httpx.MockTransport):
    def __init__(self, *, status: int = 200, payload: dict | None = None,
                 body_text: str | None = None) -> None:
        self.calls: list[httpx.Request] = []
        self._status = status
        self._payload = payload if payload is not None else {"Result": []}
        self._body_text = body_text
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self._body_text is not None:
            return httpx.Response(self._status, text=self._body_text)
        return httpx.Response(self._status, json=self._payload)


@pytest.mark.asyncio
async def test_query_entity_monta_body_e_headers() -> None:
    transport = _Transport(payload={"Result": [], "QueryId": "x"})

    result = await query_entity(
        config=_config(),
        base_url=_BASE_URL,
        doc="08.378.107/0001-07",  # mascarado — deve normalizar
        datasets="basic_data",
        transport=transport,
    )

    assert result.status_code == 200
    assert result.payload == {"Result": [], "QueryId": "x"}

    req = transport.calls[0]
    assert req.method == "POST"
    assert req.url.path == "/empresas"
    assert req.headers["AccessToken"] == "AT"
    assert req.headers["TokenId"] == "TID"

    body = json.loads(req.content)
    assert body == {
        "Datasets": "basic_data",
        "q": "doc{08378107000107}",
        "Limit": 1,
    }


@pytest.mark.asyncio
async def test_query_entity_401_vira_auth_error() -> None:
    transport = _Transport(status=401, body_text="unauthorized")
    with pytest.raises(BigDataCorpAuthError):
        await query_entity(
            config=_config(),
            base_url=_BASE_URL,
            doc="08378107000107",
            datasets="basic_data",
            transport=transport,
        )


@pytest.mark.asyncio
async def test_query_entity_500_vira_http_error() -> None:
    transport = _Transport(status=500, body_text="boom")
    with pytest.raises(BigDataCorpHttpError):
        await query_entity(
            config=_config(),
            base_url=_BASE_URL,
            doc="08378107000107",
            datasets="basic_data",
            transport=transport,
        )


@pytest.mark.asyncio
async def test_query_entity_nao_json_vira_payload_error() -> None:
    transport = _Transport(status=200, body_text="<html>nope</html>")
    with pytest.raises(BigDataCorpPayloadError):
        await query_entity(
            config=_config(),
            base_url=_BASE_URL,
            doc="08378107000107",
            datasets="basic_data",
            transport=transport,
        )


@pytest.mark.asyncio
async def test_query_entity_sem_credencial_nao_chama_rede() -> None:
    transport = _Transport()
    with pytest.raises(BigDataCorpAuthError):
        await query_entity(
            config=BigDataCorpConfig(access_token="", token_id=""),
            base_url=_BASE_URL,
            doc="08378107000107",
            datasets="basic_data",
            transport=transport,
        )
    assert transport.calls == []
