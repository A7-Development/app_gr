"""Testes do adapter SERPRO Consulta NF-e (config + client, sem rede)."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from app.modules.integracoes.adapters.data.serpro.client import SerproClient
from app.modules.integracoes.adapters.data.serpro.config import (
    PLAN_BASE_URLS,
    SerproConfig,
)
from app.modules.integracoes.adapters.data.serpro.errors import (
    SerproAuthError,
    SerproInvalidKeyError,
    SerproNotFoundError,
    SerproThrottledError,
    SerproWrongPathError,
)

CHAVE = "35210685106037000585550011234567891123456784"

NFE_BODY = {
    "nfeProc": {
        "versao": 4.0,
        "protNFe": {
            "infProt": {
                "cStat": 100,
                "xMotivo": "Autorizado o uso da NF-e",
                "nProt": 135262677425143,
                # Valor grande: json com parse_float=Decimal nao pode perder
                # precisao mesmo se o gateway emitir notacao cientifica.
                "digVal": "abc",
            }
        },
        "NFe": {"infNFe": {"total": {"ICMSTot": {"vNF": 1.234567e5}}}},
    },
    # Chave REAL da API (singular; a spec OpenAPI diz `procEventosNFe`).
    "procEventoNFe": [
        {
            "evento": {"infEvento": {"tpEvento": 110111, "dhEvento": "..."}},
            "retEvento": {"infEvento": {"cStat": "135", "nProt": "1"}},
        }
    ],
}


def _config(plan: str = "df") -> SerproConfig:
    return SerproConfig.from_dict(
        {"consumer_key": "ck", "consumer_secret": "cs", "plan": plan}
    )


# ---- Config ----------------------------------------------------------------


def test_config_resolve_base_por_plano() -> None:
    assert _config("df").base_url == PLAN_BASE_URLS["df"]
    assert _config("escalonado").base_url == PLAN_BASE_URLS["escalonado"]


def test_config_rejeita_plano_desconhecido() -> None:
    with pytest.raises(ValueError, match="Plano"):
        SerproConfig.from_dict(
            {"consumer_key": "a", "consumer_secret": "b", "plan": "premium"}
        )


def test_config_exige_credencial() -> None:
    with pytest.raises(ValueError, match="consumer_key"):
        SerproConfig.from_dict({"plan": "df"})


# ---- Client ----------------------------------------------------------------


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _token_response() -> httpx.Response:
    return httpx.Response(
        200, json={"access_token": "tok-1", "expires_in": 3300}
    )


@pytest.mark.asyncio
async def test_consulta_ok_com_token_cacheado() -> None:
    calls = {"token": 0, "nfe": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            calls["token"] += 1
            assert request.headers["Authorization"].startswith("Basic ")
            return _token_response()
        calls["nfe"] += 1
        assert request.headers["Authorization"] == "Bearer tok-1"
        assert request.headers["x-request-tag"] == "a7-credit"
        return httpx.Response(200, text=json.dumps(NFE_BODY))

    async with SerproClient(config=_config(), transport=_transport(handler)) as c:
        r1 = await c.consulta_nfe(CHAVE, request_tag="a7-credit")
        r2 = await c.consulta_nfe(CHAVE, request_tag="a7-credit")

    assert calls == {"token": 1, "nfe": 2}  # token reusado entre consultas
    assert r1.cstat == 100
    assert len(r1.eventos) == 1
    # parse_float=Decimal preserva o valor exato da notacao cientifica
    v_nf = r2.nfe_proc["NFe"]["infNFe"]["total"]["ICMSTot"]["vNF"]
    assert v_nf == Decimal("123456.7")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (400, SerproInvalidKeyError),
        (401, SerproAuthError),
        (403, SerproWrongPathError),
        (404, SerproNotFoundError),
        (429, SerproThrottledError),
    ],
)
async def test_consulta_mapeia_erros_http(status: int, exc: type) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _token_response()
        return httpx.Response(status, text="err")

    async with SerproClient(config=_config(), transport=_transport(handler)) as c:
        with pytest.raises(exc):
            await c.consulta_nfe(CHAVE)


@pytest.mark.asyncio
async def test_chave_curta_falha_antes_da_rede() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("nao deveria chamar a rede")

    async with SerproClient(config=_config(), transport=_transport(handler)) as c:
        with pytest.raises(SerproInvalidKeyError):
            await c.consulta_nfe("123")


@pytest.mark.asyncio
async def test_static_token_pula_oauth() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert not request.url.path.endswith("/token")
        assert request.headers["Authorization"] == "Bearer demo-token"
        return httpx.Response(200, text=json.dumps(NFE_BODY))

    async with SerproClient(
        config=_config(), static_token="demo-token", transport=_transport(handler)
    ) as c:
        resp = await c.consulta_nfe(CHAVE)
    assert resp.cstat == 100
