"""adapter_ping / adapter_sync — cobertura dos entrypoints do sync_runner."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.adapter import (
    adapter_ping,
    adapter_sync,
)
from app.modules.integracoes.adapters.admin.qitech.auth import _clear_cache_for_tests
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechAuthError


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
    }


@pytest.mark.asyncio
async def test_ping_ok_returns_shape() -> None:
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.adapter.get_api_token",
        return_value="SOMETOKEN",
    ):
        result = await adapter_ping(
            _config_dict(), tenant_id=uuid4(), environment=Environment.PRODUCTION
        )

    assert result["ok"] is True
    assert "latency_ms" in result
    assert result["detail"]["authenticated"] is True
    assert result["detail"]["base_url"] == "https://api.test"
    assert result["detail"]["environment"] == "production"
    assert result["adapter_version"].startswith("qitech_adapter_")


@pytest.mark.asyncio
async def test_ping_fail_never_raises() -> None:
    async def _raise(*_a, **_kw):
        raise QiTechAuthError("senha errada")

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.adapter.get_api_token",
        side_effect=_raise,
    ):
        result = await adapter_ping(_config_dict(), tenant_id=uuid4())

    assert result["ok"] is False
    assert "QiTechAuthError" in result["detail"]


@pytest.mark.asyncio
async def test_sync_auth_failure_returns_error_summary() -> None:
    async def _raise(*_a, **_kw):
        raise QiTechAuthError("rejeitada")

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.adapter.get_api_token",
        side_effect=_raise,
    ):
        summary = await adapter_sync(uuid4(), _config_dict())

    assert summary["ok"] is False
    assert summary["rows_ingested"] == 0
    assert summary["errors"]
    assert "auth" in summary["errors"][0]


@pytest.mark.asyncio
async def test_sync_auth_ok_delega_para_sync_all() -> None:
    """Apos auth OK, adapter_sync delega pro pipeline de etl.sync_all
    com a config materializada + parametros propagados."""

    async def _fake_sync_all(tenant_id, config, since, *, environment, triggered_by):
        return {
            "ok": True,
            "delegated": True,
            "tenant_id": str(tenant_id),
            "since": since.isoformat() if since else None,
            "environment": environment.value,
            "triggered_by": triggered_by,
        }

    tid = uuid4()
    with (
        patch(
            "app.modules.integracoes.adapters.admin.qitech.adapter.get_api_token",
            return_value="T",
        ),
        patch(
            "app.modules.integracoes.adapters.admin.qitech.adapter.sync_all",
            side_effect=_fake_sync_all,
        ),
    ):
        summary = await adapter_sync(tid, _config_dict(), triggered_by="user:t")

    assert summary == {
        "ok": True,
        "delegated": True,
        "tenant_id": str(tid),
        "since": None,
        "environment": "production",
        "triggered_by": "user:t",
    }
