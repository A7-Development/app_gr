"""fetch_market_report — montagem de URL, auth injetado, tratamento de erro."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import httpx
import pytest

from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.auth import _clear_cache_for_tests
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.connection import (
    build_async_client,
)
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechHttpError
from app.modules.integracoes.adapters.admin.qitech.reports import (
    TIPOS_DE_MERCADO,
    TIPOS_DE_MERCADO_CONHECIDOS,
    fetch_market_report,
)


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
    )


class _ReportTransport(httpx.MockTransport):
    """MockTransport que serve (a) o endpoint de token com um bearer fixo e
    (b) qualquer outro path com a resposta configurada.

    Coleta requests de relatorio para assertion — path, method, headers.
    """

    def __init__(
        self,
        *,
        report_body: object = None,
        report_status: int = 200,
    ) -> None:
        self.report_body = report_body
        self.report_status = report_status
        self.report_calls: list[httpx.Request] = []
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/painel/token/api":
            return httpx.Response(200, json={"apiToken": "T"})
        self.report_calls.append(request)
        if self.report_status >= 400:
            return httpx.Response(
                self.report_status, text=f"error {self.report_status}"
            )
        return httpx.Response(200, json=self.report_body)


@pytest.mark.asyncio
async def test_builds_path_with_tipo_and_data() -> None:
    transport = _ReportTransport(report_body={"assets": []})
    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=transport,
    ) as client:
        body = await fetch_market_report(
            client=client,
            tipo_de_mercado="outros-fundos",
            posicao=date(2024, 1, 15),
        )

    assert len(transport.report_calls) == 1
    req = transport.report_calls[0]
    assert req.method == "GET"
    assert req.url.path == "/v2/netreport/report/market/outros-fundos/2024-01-15"
    # x-api-key injetado pelo _ApiKeyAuth (validacao end-to-end do fluxo).
    assert req.headers["x-api-key"] == "T"
    # Nunca mandamos Bearer — QiTech retorna 500 generico, dificil debugar.
    assert "Authorization" not in req.headers
    assert body == {"assets": []}


@pytest.mark.asyncio
async def test_formats_data_as_iso_yyyy_mm_dd() -> None:
    """Doc QiTech especifica 'aaaa-mm-dd' para o path param `data`."""
    transport = _ReportTransport(report_body=[])
    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=transport,
    ) as client:
        await fetch_market_report(
            client=client,
            tipo_de_mercado="outros-fundos",
            # Meses/dias < 10 exigem zero-padding.
            posicao=date(2024, 3, 5),
        )

    assert transport.report_calls[0].url.path == (
        "/v2/netreport/report/market/outros-fundos/2024-03-05"
    )


@pytest.mark.asyncio
async def test_returns_body_as_is_for_list_response() -> None:
    """Se a QiTech devolver lista no root, retornamos lista. Zero transformacao."""
    sample = [
        {"ativo": "FDC123", "carteira": "A", "quantidade": 100},
        {"ativo": "FDC123", "carteira": "B", "quantidade": 50},
    ]
    transport = _ReportTransport(report_body=sample)
    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=transport,
    ) as client:
        body = await fetch_market_report(
            client=client,
            tipo_de_mercado="outros-fundos",
            posicao=date(2024, 1, 15),
        )

    assert body == sample


@pytest.mark.asyncio
async def test_http_4xx_raises() -> None:
    transport = _ReportTransport(report_status=404)
    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=transport,
    ) as client:
        with pytest.raises(QiTechHttpError) as exc:
            await fetch_market_report(
                client=client,
                tipo_de_mercado="outros-fundos",
                posicao=date(2024, 1, 15),
            )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_http_5xx_raises() -> None:
    transport = _ReportTransport(report_status=503)
    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=transport,
    ) as client:
        with pytest.raises(QiTechHttpError) as exc:
            await fetch_market_report(
                client=client,
                tipo_de_mercado="outros-fundos",
                posicao=date(2024, 1, 15),
            )

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_rf_tipo_de_mercado_also_works() -> None:
    """`rf` (renda fixa) vai literal no path igual `outros-fundos`."""
    transport = _ReportTransport(report_body={"ativos": []})
    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=transport,
    ) as client:
        await fetch_market_report(
            client=client,
            tipo_de_mercado="rf",
            posicao=date(2024, 1, 15),
        )

    assert transport.report_calls[0].url.path == (
        "/v2/netreport/report/market/rf/2024-01-15"
    )


def test_catalogo_contem_23_tipos_conhecidos() -> None:
    """Snapshot da lista completa de tipos passada pela doc QiTech.

    Se novo tipo entrar, o teste falha e obriga atualizar aqui + docs.
    """
    esperado = {
        "outros-fundos",
        "rf",
        "rv",
        "rv-opcoes",
        "rv-opcoes-flexiveis",
        "rv-emprestimo-acoes",
        "rv-emprestimo-acoes-inadimplentes",
        "rf-fidc",
        "rf-compromissadas",
        "futuros",
        "opcoes-futuro",
        "swap",
        "termo",
        "termo-rv",
        "cambio",
        "tesouraria",
        "conta-corrente",
        "cpr",
        "demonstrativo-caixa",
        "outros-ativos",
        "outros-emprestimos",
        "rentabilidade",
        "mec",
    }
    assert set(TIPOS_DE_MERCADO) == esperado
    # Nenhum codigo duplicado (tupla de pares -> dict sem colisao).
    mapping = dict(TIPOS_DE_MERCADO_CONHECIDOS)
    assert len(mapping) == len(TIPOS_DE_MERCADO_CONHECIDOS)
    # Labels PT canonicos — regressao contra reordenacao / typo.
    assert mapping["outros-fundos"] == "Outros fundos"
    assert mapping["rf"] == "Renda fixa"
    assert mapping["mec"] == "MEC (mapa evolutivo de cotas)"


@pytest.mark.asyncio
async def test_tipo_multi_hifen_preserva_path_literal() -> None:
    """Tipos com varios hifens (ex.: rv-emprestimo-acoes-inadimplentes)
    viajam literalmente no path — sem URL-encoding, sem conversao.
    """
    transport = _ReportTransport(report_body=[])
    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=transport,
    ) as client:
        await fetch_market_report(
            client=client,
            tipo_de_mercado="rv-emprestimo-acoes-inadimplentes",
            posicao=date(2024, 1, 15),
        )

    assert transport.report_calls[0].url.path == (
        "/v2/netreport/report/market/"
        "rv-emprestimo-acoes-inadimplentes/2024-01-15"
    )


@pytest.mark.asyncio
async def test_http_400_com_shape_canonico_retorna_body_vazio() -> None:
    """Caso especial QiTech: 400 com body `{relatorios: {}, _links, message}`
    NAO e erro — e a forma que a QiTech avisa "sem dados pra esse mercado
    neste dia". Observado em producao (2026-04-24) em rv, futuros, swap,
    quando o tenant nao tem portfolio no mercado. ETL precisa registrar
    "zero posicoes", diferente de "falha de integracao".
    """
    empty_body = {
        "relatórios": {},
        "_links": {},
        "message": "Não há resultados para os parâmetros informados.",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/painel/token/api":
            return httpx.Response(200, json={"apiToken": "T"})
        return httpx.Response(400, json=empty_body)

    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=httpx.MockTransport(handler),
    ) as client:
        body = await fetch_market_report(
            client=client,
            tipo_de_mercado="rv",
            posicao=date(2026, 1, 13),
        )

    assert body == empty_body


@pytest.mark.asyncio
async def test_http_400_sem_shape_canonico_levanta() -> None:
    """400 com payload arbitrario (ex.: request malformado de verdade) ainda
    e erro — so o shape canonico QiTech e tratado como sucesso-vazio.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/painel/token/api":
            return httpx.Response(200, json={"apiToken": "T"})
        return httpx.Response(400, json={"error": "bad request"})

    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(QiTechHttpError) as exc:
            await fetch_market_report(
                client=client,
                tipo_de_mercado="rv",
                posicao=date(2026, 1, 13),
            )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_non_json_response_raises() -> None:
    """Proteção: se a QiTech devolver 200 com HTML/texto, erro claro."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/painel/token/api":
            return httpx.Response(200, json={"apiToken": "T"})
        return httpx.Response(200, text="<html>oops</html>")

    async with build_async_client(
        tenant_id=uuid4(),
        environment=Environment.PRODUCTION,
        config=_cfg(),
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(QiTechHttpError, match="nao-JSON"):
            await fetch_market_report(
                client=client,
                tipo_de_mercado="outros-fundos",
                posicao=date(2024, 1, 15),
            )
