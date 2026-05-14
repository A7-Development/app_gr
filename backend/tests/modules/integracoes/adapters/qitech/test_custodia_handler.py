"""Custodia handler: data unitaria + 4xx canonico nao levanta.

Cobre os 2 bugs do auto-sync recorrente identificados em 2026-05-14:

1. `_fetch_json` levantava em qualquer 4xx, impedindo o adapter de gravar raw
   quando a QiTech respondia 400/404 com envelope vazio (`{"message": "..."}`).
   Sem raw, o coverage marcava o dia como gap; o reconciler enfileirava
   BackfillJob; o ciclo se repetia a cada 30 min indefinidamente.

2. `_handler_custodia_periodo` invocava o sync_fn com janela ampla
   `(since, hoje)`, gravando 1 raw em `data_posicao=data_final`. O coverage
   indexado por data nao casava com as datas intermediarias — todas viravam
   gap, reconciler reenfileirava em loop.

Estes testes garantem a regressao das 2 correcoes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.integracoes.adapters.admin.qitech import adapter, custodia
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechHttpError


def _mock_client(status: int, json_value=None, text: str = "") -> MagicMock:
    """Constroi mock do httpx.AsyncClient retornado por build_async_client."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    if isinstance(json_value, Exception):
        mock_resp.json.side_effect = json_value
    else:
        mock_resp.json.return_value = json_value
    mock_resp.text = text

    client = MagicMock()
    client.get = AsyncMock(return_value=mock_resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


# ----- _fetch_json: 4xx canonico vs erro real ---------------------------------


@pytest.mark.asyncio
async def test_fetch_json_400_returns_body_without_raising() -> None:
    """400 com body JSON canonico (envelope vazio) deve devolver (body, 400).

    Regressao do bug que enfileirava o mesmo dia em loop: sem body devolvido,
    o adapter nao grava raw, coverage nao ve nada, reconciler reenfileira.
    """
    body_canonico = {"message": "Nao ha dados para essa data", "relatorios": {}}
    client = _mock_client(400, body_canonico, "{}")

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.custodia.build_async_client",
        return_value=client,
    ):
        body, status = await custodia._fetch_json(
            tenant_id=uuid4(), environment=None, config=None, path="/test"
        )

    assert status == 400
    assert body == body_canonico


@pytest.mark.asyncio
async def test_fetch_json_404_returns_body_without_raising() -> None:
    """404 com body JSON: mesma semantica que 400."""
    body = {"error": "Not found"}
    client = _mock_client(404, body, "{}")

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.custodia.build_async_client",
        return_value=client,
    ):
        result_body, status = await custodia._fetch_json(
            tenant_id=uuid4(), environment=None, config=None, path="/test"
        )

    assert status == 404
    assert result_body == body


@pytest.mark.asyncio
async def test_fetch_json_404_non_json_returns_synthetic_payload() -> None:
    """4xx sem body JSON parseavel ainda devolve payload sintetico.

    Razao: sem raw o reconciler enfileira em loop. Preferimos gravar marca
    da tentativa (`{"_non_json": "..."}`) a perder o registro.
    """
    import json

    client = _mock_client(404, json.JSONDecodeError("not json", "", 0), "Not Found")

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.custodia.build_async_client",
        return_value=client,
    ):
        body, status = await custodia._fetch_json(
            tenant_id=uuid4(), environment=None, config=None, path="/test"
        )

    assert status == 404
    assert body == {"_non_json": "Not Found"}


@pytest.mark.asyncio
async def test_fetch_json_401_raises() -> None:
    """401 (auth) e erro real — continua levantando."""
    client = _mock_client(401, {"error": "unauthorized"}, "unauthorized")

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.custodia.build_async_client",
        return_value=client,
    ):
        with pytest.raises(QiTechHttpError) as exc_info:
            await custodia._fetch_json(
                tenant_id=uuid4(), environment=None, config=None, path="/test"
            )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_fetch_json_500_raises() -> None:
    """5xx (erro do servidor) levanta."""
    client = _mock_client(500, {}, "server error")

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.custodia.build_async_client",
        return_value=client,
    ):
        with pytest.raises(QiTechHttpError) as exc_info:
            await custodia._fetch_json(
                tenant_id=uuid4(), environment=None, config=None, path="/test"
            )

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_fetch_json_200_returns_body() -> None:
    """200 normal devolve body e status 200."""
    body = {"liquidadosBaixados": [{"idRecebivel": "X"}]}
    client = _mock_client(200, body, "{}")

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.custodia.build_async_client",
        return_value=client,
    ):
        result_body, status = await custodia._fetch_json(
            tenant_id=uuid4(), environment=None, config=None, path="/test"
        )

    assert status == 200
    assert result_body == body


@pytest.mark.asyncio
async def test_fetch_json_200_invalid_json_raises() -> None:
    """200 com body nao-JSON ainda levanta (erro de contrato, nao 'sem dado')."""
    import json

    client = _mock_client(200, json.JSONDecodeError("invalid", "", 0), "broken")

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.custodia.build_async_client",
        return_value=client,
    ):
        with pytest.raises(QiTechHttpError):
            await custodia._fetch_json(
                tenant_id=uuid4(), environment=None, config=None, path="/test"
            )


# ----- _handler_custodia_periodo: data unitaria, nao janela -------------------


@pytest.mark.asyncio
async def test_handler_custodia_periodo_backfill_data_unitaria() -> None:
    """Backfill com since=22/4 deve chamar sync_fn(data_inicial=22/4, data_final=22/4).

    Antes da correcao, o handler chamava com janela `(since, hoje)`, gravando
    raw em `data_posicao=hoje`. Coverage indexado por data nao casava com
    22/4 — gap eterno, reconciler em loop.
    """
    sync_fn = AsyncMock(return_value={"name": "liquidados-baixados", "ok": True})

    with patch.object(
        adapter, "resolve_cnpj_by_ua_id", AsyncMock(return_value="12345678000100")
    ):
        steps = await adapter._handler_custodia_periodo(
            name="custodia.liquidados_baixados",
            sync_fn=sync_fn,
            tenant_id=uuid4(),
            config=None,
            environment=None,
            unidade_administrativa_id=uuid4(),
            since=date(2026, 4, 22),
        )

    assert len(steps) == 1
    sync_fn.assert_awaited_once()
    kwargs = sync_fn.await_args.kwargs
    assert kwargs["data_inicial"] == date(2026, 4, 22)
    assert kwargs["data_final"] == date(2026, 4, 22)


@pytest.mark.asyncio
async def test_handler_custodia_periodo_default_uses_d_minus_1() -> None:
    """Sync diario sem `since` usa D-1 e mantem data_inicial=data_final."""
    sync_fn = AsyncMock(return_value={"name": "aquisicao-consolidada", "ok": True})

    with patch.object(
        adapter, "resolve_cnpj_by_ua_id", AsyncMock(return_value="12345678000100")
    ):
        await adapter._handler_custodia_periodo(
            name="custodia.aquisicao_consolidada",
            sync_fn=sync_fn,
            tenant_id=uuid4(),
            config=None,
            environment=None,
            unidade_administrativa_id=uuid4(),
            since=None,
        )

    expected = (datetime.now(UTC) - timedelta(days=1)).date()
    kwargs = sync_fn.await_args.kwargs
    assert kwargs["data_inicial"] == expected
    assert kwargs["data_final"] == expected
    assert kwargs["data_inicial"] == kwargs["data_final"]


@pytest.mark.asyncio
async def test_handler_custodia_periodo_sem_ua_falha_cedo() -> None:
    """Sem UA, devolve step_error sem chamar sync_fn (custodia.* exige UA)."""
    sync_fn = AsyncMock()

    steps = await adapter._handler_custodia_periodo(
        name="custodia.liquidados_baixados",
        sync_fn=sync_fn,
        tenant_id=uuid4(),
        config=None,
        environment=None,
        unidade_administrativa_id=None,
        since=date(2026, 4, 22),
    )

    sync_fn.assert_not_awaited()
    assert steps[0]["ok"] is False
    assert "UA obrigatoria" in steps[0]["errors"][0]


@pytest.mark.asyncio
async def test_handler_custodia_periodo_ua_sem_cnpj() -> None:
    """UA configurada mas sem CNPJ cadastrado: step_error sem chamar sync_fn."""
    sync_fn = AsyncMock()
    with patch.object(adapter, "resolve_cnpj_by_ua_id", AsyncMock(return_value=None)):
        steps = await adapter._handler_custodia_periodo(
            name="custodia.aquisicao_consolidada",
            sync_fn=sync_fn,
            tenant_id=uuid4(),
            config=None,
            environment=None,
            unidade_administrativa_id=uuid4(),
            since=date(2026, 4, 22),
        )

    sync_fn.assert_not_awaited()
    assert steps[0]["ok"] is False
    assert "sem CNPJ" in steps[0]["errors"][0]
