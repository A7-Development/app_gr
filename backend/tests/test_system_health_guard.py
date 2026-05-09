"""Unit tests for `require_system_health_token` guard.

Pure unit tests — no DB, no FastAPI runtime. Calls the guard function
directly with synthetic Settings + Authorization header values.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.system_health_guard import require_system_health_token


def _settings(token: str) -> Settings:
    """Build a Settings instance bypassing env-var validation.

    `model_construct` skips field validation — fine for tests since we're
    only exercising the guard's branching, not pydantic validators.
    """
    return Settings.model_construct(SYSTEM_HEALTH_TOKEN=token)


@pytest.mark.asyncio
async def test_returns_503_when_token_not_configured():
    with pytest.raises(HTTPException) as exc:
        await require_system_health_token(
            settings=_settings(""), authorization=None
        )
    assert exc.value.status_code == 503
    assert "nao configurado" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_returns_401_when_header_missing():
    with pytest.raises(HTTPException) as exc:
        await require_system_health_token(
            settings=_settings("server-token"), authorization=None
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_returns_401_when_header_not_bearer():
    with pytest.raises(HTTPException) as exc:
        await require_system_health_token(
            settings=_settings("server-token"),
            authorization="Token server-token",
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_returns_401_when_token_mismatch():
    with pytest.raises(HTTPException) as exc:
        await require_system_health_token(
            settings=_settings("server-token"),
            authorization="Bearer wrong-token",
        )
    assert exc.value.status_code == 401
    assert "invalido" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_passes_when_token_matches():
    # Should return None silently.
    result = await require_system_health_token(
        settings=_settings("server-token"),
        authorization="Bearer server-token",
    )
    assert result is None


@pytest.mark.asyncio
async def test_constant_time_compare_doesnt_short_circuit():
    """Token errado de mesmo tamanho ainda eh rejeitado (sanity check do
    secrets.compare_digest)."""
    with pytest.raises(HTTPException) as exc:
        await require_system_health_token(
            settings=_settings("server-token-12345678"),
            authorization="Bearer server-token-XXXXXXXX",
        )
    assert exc.value.status_code == 401
