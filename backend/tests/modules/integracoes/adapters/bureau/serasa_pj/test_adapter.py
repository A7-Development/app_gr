"""adapter_ping / adapter_sync — entrypoints registrados no sync_runner."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from app.core.enums import Environment
from app.modules.integracoes.adapters.bureau.serasa_pj.adapter import (
    adapter_ping,
    adapter_sync,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.auth import (
    _clear_cache_for_tests,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.errors import (
    SerasaPjAuthError,
    SerasaPjConfigError,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    _clear_cache_for_tests()
    yield
    _clear_cache_for_tests()


def _config_dict() -> dict:
    return {
        "base_url": "https://api.test",
        "client_id": "u",
        "client_secret": "p",
        "retailer_document_id": "12345678000199",
    }


@pytest.mark.asyncio
async def test_ping_ok_returns_shape() -> None:
    with patch(
        "app.modules.integracoes.adapters.bureau.serasa_pj.adapter.get_access_token",
        return_value="SOMETOKEN_LONG",
    ):
        result = await adapter_ping(
            _config_dict(),
            tenant_id=uuid4(),
            environment=Environment.PRODUCTION,
        )

    assert result["ok"] is True
    assert "latency_ms" in result
    detail = result["detail"]
    assert detail["authenticated"] is True
    assert detail["base_url"] == "https://api.test"
    assert detail["environment"] == "production"
    assert detail["retailer_document_id_set"] is True
    assert detail["score_model_pj"] == "H4PJ"
    assert detail["default_report_type"] == "RELATORIO_AVANCADO_PJ_ANALITICO"
    assert result["adapter_version"].startswith("serasa_pj_adapter_")


@pytest.mark.asyncio
async def test_ping_auth_fail_returns_ok_false() -> None:
    async def _raise(*_a, **_kw):
        raise SerasaPjAuthError("rejeitada")

    with patch(
        "app.modules.integracoes.adapters.bureau.serasa_pj.adapter.get_access_token",
        side_effect=_raise,
    ):
        result = await adapter_ping(_config_dict(), tenant_id=uuid4())

    assert result["ok"] is False
    assert "SerasaPjAuthError" in result["detail"]


@pytest.mark.asyncio
async def test_ping_missing_retailer_returns_config_error() -> None:
    """Sem retailer_document_id, has_credentials() falha — ping reporta sem bater na rede."""
    bad_config = {
        "base_url": "https://api.test",
        "client_id": "u",
        "client_secret": "p",
        "retailer_document_id": "",
    }

    # Nao precisamos mockar — o get_access_token vai levantar SerasaPjConfigError
    # antes de tentar rede, e o adapter_ping captura.
    result = await adapter_ping(bad_config, tenant_id=uuid4())

    assert result["ok"] is False
    assert "SerasaPjConfigError" in result["detail"]


@pytest.mark.asyncio
async def test_ping_unexpected_exception_returns_ok_false() -> None:
    """Defesa: erros nao-tipados tambem viram ok=False (UI nao quebra)."""

    async def _raise(*_a, **_kw):
        raise RuntimeError("internal weirdness")

    with patch(
        "app.modules.integracoes.adapters.bureau.serasa_pj.adapter.get_access_token",
        side_effect=_raise,
    ):
        result = await adapter_ping(_config_dict(), tenant_id=uuid4())

    assert result["ok"] is False
    assert "RuntimeError" in result["detail"]


@pytest.mark.asyncio
async def test_sync_returns_explanatory_stub() -> None:
    """Bureau adapters nao tem sync periodico — `adapter_sync` retorna
    summary com errors[0] explicando que e fonte sob demanda.
    """
    summary = await adapter_sync(uuid4(), _config_dict())

    assert summary["ok"] is False
    assert summary["rows_ingested"] == 0
    assert summary["elapsed_seconds"] == 0.0
    assert summary["steps"] == []
    assert summary["errors"]
    assert "sob demanda" in summary["errors"][0].lower()
    assert summary["adapter_version"].startswith("serasa_pj_adapter_")


@pytest.mark.asyncio
async def test_sync_does_not_call_network() -> None:
    """O stub nao deve nem tentar autenticar — bureau e on-demand."""
    with patch(
        "app.modules.integracoes.adapters.bureau.serasa_pj.adapter.get_access_token"
    ) as mock_auth:
        await adapter_sync(uuid4(), _config_dict())
    mock_auth.assert_not_called()


@pytest.mark.asyncio
async def test_ping_signature_accepts_unused_ua_kwarg() -> None:
    """Compat de interface com QiTech: sync_runner sempre passa
    unidade_administrativa_id, mesmo que o adapter ignore.
    """
    with patch(
        "app.modules.integracoes.adapters.bureau.serasa_pj.adapter.get_access_token",
        return_value="T",
    ):
        result = await adapter_ping(
            _config_dict(),
            tenant_id=uuid4(),
            environment=Environment.SANDBOX,
            unidade_administrativa_id=uuid4(),
        )
    assert result["ok"] is True
    assert result["detail"]["environment"] == "sandbox"


def test_serasa_config_error_is_excecao_tipada() -> None:
    """Smoke check do tipo — SerasaPjConfigError existe e e subclasse base."""
    from app.modules.integracoes.adapters.bureau.serasa_pj.errors import (
        SerasaPjAdapterError,
    )

    assert issubclass(SerasaPjConfigError, SerasaPjAdapterError)
