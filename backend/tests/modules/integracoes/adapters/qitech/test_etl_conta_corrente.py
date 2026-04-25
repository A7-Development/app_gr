"""ETL QiTech conta-corrente -- integracao end-to-end (DB real).

Mesmo padrao do test_etl_outros_fundos: mock transport HTTP + DB real.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
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
from app.modules.integracoes.adapters.admin.qitech.etl import (
    sync_conta_corrente,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION
from app.shared.identity.tenant import Tenant
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio
from app.warehouse.saldo_conta_corrente import SaldoContaCorrente

SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-13"
    / "conta-corrente.json"
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


@pytest.fixture
def empty_envelope() -> dict:
    return {
        "relatórios": {},
        "_links": {},
        "message": "Não há resultados para os parâmetros informados.",
    }


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
async def test_sync_conta_corrente_payload_real_grava_raw_e_canonico(
    tenant_a: Tenant, real_payload: dict
):
    transport = _build_transport(body=real_payload, status=200)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.etl.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)
        step = await sync_conta_corrente(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            data_posicao=DATA_POSICAO,
        )

    assert step["ok"] is True
    assert step["raw_http_status"] == 200
    assert step["raw_persisted"] is True
    assert step["canonical_rows_upserted"] == 3
    assert step["errors"] == []

    async with AsyncSessionLocal() as db:
        raw = (
            await db.execute(
                select(QiTechRawRelatorio).where(
                    QiTechRawRelatorio.tenant_id == tenant_a.id,
                    QiTechRawRelatorio.tipo_de_mercado == "conta-corrente",
                )
            )
        ).scalar_one()
        assert raw.payload == real_payload
        assert raw.fetched_by_version == ADAPTER_VERSION

        canon = (
            await db.execute(
                select(SaldoContaCorrente).where(
                    SaldoContaCorrente.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(canon) == 3
        codigos = {r.codigo for r in canon}
        assert codigos == {"BRADESCO", "CONCILIA", "SOCOPA"}
        # Saldo negativo de CONCILIA preservado.
        concilia = next(r for r in canon if r.codigo == "CONCILIA")
        assert concilia.valor_total == Decimal("-80310.61")


@pytest.mark.asyncio
async def test_sync_conta_corrente_envelope_vazio(
    tenant_a: Tenant, empty_envelope: dict
):
    transport = _build_transport(body=empty_envelope, status=400)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.etl.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)
        step = await sync_conta_corrente(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            data_posicao=DATA_POSICAO,
        )

    assert step["ok"] is True
    assert step["raw_http_status"] == 400
    assert step["raw_persisted"] is True
    assert step["canonical_rows_upserted"] == 0


@pytest.mark.asyncio
async def test_sync_conta_corrente_idempotente(
    tenant_a: Tenant, real_payload: dict
):
    transport = _build_transport(body=real_payload, status=200)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.etl.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)
        await sync_conta_corrente(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            data_posicao=DATA_POSICAO,
        )
        await sync_conta_corrente(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            data_posicao=DATA_POSICAO,
        )

    async with AsyncSessionLocal() as db:
        canon = (
            await db.execute(
                select(SaldoContaCorrente).where(
                    SaldoContaCorrente.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(canon) == 3


@pytest.mark.asyncio
async def test_sync_conta_corrente_isolamento_tenant(
    tenant_a: Tenant, tenant_b: Tenant, real_payload: dict
):
    transport = _build_transport(body=real_payload, status=200)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.etl.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)
        await sync_conta_corrente(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            data_posicao=DATA_POSICAO,
        )

    async with AsyncSessionLocal() as db:
        b_canon = (
            await db.execute(
                select(SaldoContaCorrente).where(
                    SaldoContaCorrente.tenant_id == tenant_b.id
                )
            )
        ).scalars().all()
        assert b_canon == []
