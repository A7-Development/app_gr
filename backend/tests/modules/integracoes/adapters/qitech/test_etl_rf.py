"""ETL QiTech rf -- E2E."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.auth import (
    _clear_cache_for_tests,
)
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.etl import sync_rf
from app.shared.identity.tenant import Tenant
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa

SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-13"
    / "rf.json"
)
DATA_POSICAO = date(2026, 1, 13)


@pytest.fixture(autouse=True)
def _reset_token_cache():
    _clear_cache_for_tests()
    yield
    _clear_cache_for_tests()


@pytest.fixture
def real_payload() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def _cfg() -> QiTechConfig:
    return QiTechConfig(
        base_url="https://api.test", client_id="u", client_secret="p"
    )


def _build_transport(*, body: object, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/painel/token/api":
            return httpx.Response(200, json={"apiToken": "T"})
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_sync_rf_payload_real(tenant_a: Tenant, real_payload: dict):
    transport = _build_transport(body=real_payload)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.etl.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)
        step = await sync_rf(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            data_posicao=DATA_POSICAO,
        )

    assert step["ok"]
    assert step["canonical_rows_upserted"] == 26
    async with AsyncSessionLocal() as db:
        canon = (
            await db.execute(
                select(PosicaoRendaFixa).where(
                    PosicaoRendaFixa.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(canon) == 26
        # 3 indexadores: CDI, IPCA, PRE.
        indexadores = {r.indexador for r in canon}
        assert indexadores == {"CDI", "IPCA", "PRE"}


@pytest.mark.asyncio
async def test_sync_rf_isolamento(
    tenant_a: Tenant, tenant_b: Tenant, real_payload: dict
):
    transport = _build_transport(body=real_payload)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.etl.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)
        await sync_rf(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            data_posicao=DATA_POSICAO,
        )
    async with AsyncSessionLocal() as db:
        b = (
            await db.execute(
                select(PosicaoRendaFixa).where(
                    PosicaoRendaFixa.tenant_id == tenant_b.id
                )
            )
        ).scalars().all()
        assert b == []
