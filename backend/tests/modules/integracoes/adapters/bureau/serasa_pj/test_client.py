"""query_pj_analitico — query string, headers, payload, downgrade, erros.

Adapter Serasa PJ usa GET com:
- `reportName` + `reportParameters` (JSON base64-encoded com segmentCode)
  em QUERY STRING
- CNPJ alvo em HEADER `X-Document-id`
- CNPJ consultante em HEADER `X-Retailer-Document-Id`
- Sem body
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.core.enums import Environment
from app.modules.integracoes.adapters.bureau.serasa_pj.auth import (
    _clear_cache_for_tests,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.client import (
    BureauQueryResult,
    query_pj_analitico,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.config import (
    SerasaPjConfig,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.errors import (
    SerasaPjConfigError,
    SerasaPjHttpError,
    SerasaPjReciprocityDowngradeError,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    _clear_cache_for_tests()
    yield
    _clear_cache_for_tests()


def _config(retailer: str = "12345678000199") -> SerasaPjConfig:
    return SerasaPjConfig(
        base_url="https://api.test",
        client_id="u",
        client_secret="p",
        retailer_document_id=retailer,
        token_ttl_seconds=3600,
        token_refresh_skew_seconds=60,
    )


class _Transport(httpx.MockTransport):
    """Mock que serve login + endpoint de relatorio.

    - `/security/iam/v1/client-identities/login` -> token sequencial.
    - qualquer outro path -> resposta de relatorio configuravel.
    """

    def __init__(
        self,
        *,
        report_payload: dict | None = None,
        report_status: int = 200,
        report_status_first: int | None = None,
    ) -> None:
        self.token_calls: int = 0
        self.report_calls: list[httpx.Request] = []
        self._report_payload = report_payload or {
            "reportName": "RELATORIO_AVANCADO_PJ_ANALITICO",
            "registrationData": {"documentId": "12345678000199"},
        }
        self._report_status = report_status
        self._report_status_first = report_status_first
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/security/iam/v1/client-identities/login":
            self.token_calls += 1
            # Prod (validado 2026-05-01): camelCase OAuth2 padrao.
            return httpx.Response(
                200,
                json={
                    "accessToken": f"TOKEN-{self.token_calls}",
                    "tokenType": "Bearer",
                    "expiresIn": "3600",
                    "scope": "credit-services",
                },
            )

        self.report_calls.append(request)
        # Permite testar refresh em 401: primeira call falha, segunda passa.
        if (
            self._report_status_first is not None
            and len(self.report_calls) == 1
        ):
            return httpx.Response(
                self._report_status_first, text=f"err {self._report_status_first}"
            )

        if self._report_status >= 400:
            return httpx.Response(
                self._report_status, text=f"err {self._report_status}"
            )
        return httpx.Response(self._report_status, json=self._report_payload)


@pytest.mark.asyncio
async def test_query_returns_bureau_result_with_payload() -> None:
    transport = _Transport()

    result = await query_pj_analitico(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(),
        cnpj="12.345.678/0001-99",
        transport=transport,
    )

    assert isinstance(result, BureauQueryResult)
    assert result.status_code == 200
    assert result.requested_report == "RELATORIO_AVANCADO_PJ_ANALITICO"
    assert result.actual_report_returned == "RELATORIO_AVANCADO_PJ_ANALITICO"
    assert result.adapter_version.startswith("serasa_pj_adapter_")
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_uses_get_method_without_body() -> None:
    """Adapter usa GET (nao POST) — confirmado contra prod 2026-05-01."""
    transport = _Transport()

    await query_pj_analitico(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(),
        cnpj="12.345.678/0001-99",
        transport=transport,
    )
    req = transport.report_calls[0]
    assert req.method == "GET"
    assert req.content == b""


@pytest.mark.asyncio
async def test_query_string_carries_report_name_and_parameters() -> None:
    """`reportName` em query + `reportParameters` JSON base64-encoded
    carregando segmentCode."""
    import base64
    import json as _json

    transport = _Transport()

    await query_pj_analitico(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(),
        cnpj="12.345.678/0001-99",
        transport=transport,
    )
    req = transport.report_calls[0]
    qs = dict(req.url.params)
    assert qs["reportName"] == "RELATORIO_AVANCADO_PJ_ANALITICO"
    # reportParameters e base64 de
    # {"reportParameters": [{"name": "segmentCode", "value": "028"}]}
    decoded = _json.loads(base64.b64decode(qs["reportParameters"]))
    assert decoded["reportParameters"] == [
        {"name": "segmentCode", "value": "028"}
    ]


@pytest.mark.asyncio
async def test_cnpj_goes_in_x_document_id_header() -> None:
    """CNPJ alvo viaja no HEADER `X-Document-id`, nao em query."""
    transport = _Transport()

    await query_pj_analitico(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(),
        cnpj="12.345.678/0001-99",
        transport=transport,
    )
    req = transport.report_calls[0]
    # CNPJ stripado de mascara antes de enviar.
    assert req.headers.get("X-Document-id") == "12345678000199"
    # Nao deve aparecer em query string (anti-regressao).
    assert "documentId" not in dict(req.url.params)


@pytest.mark.asyncio
async def test_rejects_invalid_cnpj() -> None:
    transport = _Transport()
    with pytest.raises(SerasaPjConfigError, match="CNPJ invalido"):
        await query_pj_analitico(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(),
            cnpj="123",
            transport=transport,
        )


@pytest.mark.asyncio
async def test_rejects_missing_credentials() -> None:
    transport = _Transport()
    cfg = SerasaPjConfig(
        base_url="https://api.test",
        client_id="",
        client_secret="",
        retailer_document_id="",
    )
    with pytest.raises(SerasaPjConfigError, match="incompleta"):
        await query_pj_analitico(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=cfg,
            cnpj="12345678000199",
            transport=transport,
        )


@pytest.mark.asyncio
async def test_injects_bearer_and_retailer_headers() -> None:
    transport = _Transport()

    await query_pj_analitico(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(retailer="98765432000111"),
        cnpj="12345678000199",
        transport=transport,
    )

    req = transport.report_calls[0]
    assert req.headers.get("Authorization", "").startswith("Bearer TOKEN-")
    assert req.headers.get("X-Retailer-Document-Id") == "98765432000111"


@pytest.mark.asyncio
async def test_cost_center_header_truncated_to_12_chars() -> None:
    transport = _Transport()

    result = await query_pj_analitico(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(),
        cnpj="12345678000199",
        cost_center="dossie-12345-extra-stuff",
        transport=transport,
    )

    req = transport.report_calls[0]
    sent = req.headers.get("X-Cost-Center")
    assert sent is not None
    assert len(sent) <= 12
    assert result.cost_center == sent


@pytest.mark.asyncio
async def test_cost_center_omitted_when_none() -> None:
    transport = _Transport()
    await query_pj_analitico(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(),
        cnpj="12345678000199",
        transport=transport,
    )
    req = transport.report_calls[0]
    assert req.headers.get("X-Cost-Center") is None


@pytest.mark.asyncio
async def test_reciprocity_downgrade_detected_in_result() -> None:
    """Quando reciprocidade quebra, Serasa devolve relatorio sintetico no
    lugar do analitico — o client expoe ambos no result.
    """
    transport = _Transport(
        report_payload={
            "reportName": "RELATORIO_AVANCADO_PJ",  # sintetico, nao analitico
            "registrationData": {},
        },
    )

    result = await query_pj_analitico(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(),
        cnpj="12345678000199",
        transport=transport,
    )

    assert result.requested_report == "RELATORIO_AVANCADO_PJ_ANALITICO"
    assert result.actual_report_returned == "RELATORIO_AVANCADO_PJ"


@pytest.mark.asyncio
async def test_reciprocity_downgrade_raises_when_strict() -> None:
    transport = _Transport(
        report_payload={"reportName": "RELATORIO_AVANCADO_PJ"},
    )

    with pytest.raises(SerasaPjReciprocityDowngradeError) as exc:
        await query_pj_analitico(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(),
            cnpj="12345678000199",
            transport=transport,
            raise_on_downgrade=True,
        )

    assert exc.value.requested == "RELATORIO_AVANCADO_PJ_ANALITICO"
    assert exc.value.received == "RELATORIO_AVANCADO_PJ"


@pytest.mark.asyncio
async def test_4xx_raises_http_error() -> None:
    transport = _Transport(report_status=429)

    with pytest.raises(SerasaPjHttpError) as exc:
        await query_pj_analitico(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(),
            cnpj="12345678000199",
            transport=transport,
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_5xx_raises_http_error() -> None:
    transport = _Transport(report_status=503)
    with pytest.raises(SerasaPjHttpError) as exc:
        await query_pj_analitico(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(),
            cnpj="12345678000199",
            transport=transport,
        )
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_401_invalidates_cache_and_retries() -> None:
    """Connection layer: 401 no relatorio -> invalida token + reenvia uma vez."""
    transport = _Transport(report_status_first=401)

    result = await query_pj_analitico(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_config(),
        cnpj="12345678000199",
        transport=transport,
    )

    assert result.status_code == 200
    # Login chamado 2 vezes (primeira para token inicial, segunda apos invalidate).
    assert transport.token_calls == 2
    # Relatorio: 1 falha + 1 retry = 2 chamadas.
    assert len(transport.report_calls) == 2


@pytest.mark.asyncio
async def test_non_json_response_raises_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/security/iam/v1/client-identities/login":
            return httpx.Response(
                200,
                json={
                    "accessToken": "T",
                    "tokenType": "Bearer",
                    "expiresIn": "3600",
                },
            )
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(SerasaPjHttpError, match="nao-JSON"):
        await query_pj_analitico(
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
            config=_config(),
            cnpj="12345678000199",
            transport=httpx.MockTransport(handler),
        )
