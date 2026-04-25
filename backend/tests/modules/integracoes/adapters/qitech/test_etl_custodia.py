"""ETL custodia -- E2E pros 3 endpoints sincronos /v2/fidc-custodia/."""

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
from app.modules.integracoes.adapters.admin.qitech.custodia import (
    sync_aquisicao_consolidada,
    sync_detalhes_operacoes,
    sync_liquidados_baixados,
)
from app.shared.identity.tenant import Tenant
from app.warehouse.aquisicao_recebivel import AquisicaoRecebivel
from app.warehouse.liquidacao_recebivel import LiquidacaoRecebivel
from app.warehouse.operacao_remessa import OperacaoRemessa
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio

SAMPLES_DIR = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "fidc-custodia-2026-01-01-2026-01-08"
)
CNPJ = "42449234000160"
DATA_INI = date(2026, 1, 1)
DATA_FIM = date(2026, 1, 8)


@pytest.fixture(autouse=True)
def _reset_token_cache():
    _clear_cache_for_tests()
    yield
    _clear_cache_for_tests()


def _cfg() -> QiTechConfig:
    return QiTechConfig(
        base_url="https://api.test", client_id="u", client_secret="p"
    )


def _build_transport(*, payload_by_path: dict[str, object]) -> httpx.MockTransport:
    """Mock que serve token endpoint + N paths configurados via dict."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/painel/token/api":
            return httpx.Response(200, json={"apiToken": "T"})
        body = payload_by_path.get(request.url.path)
        if body is None:
            return httpx.Response(404, json={"error": "not mocked"})
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_sync_aquisicao_consolidada_payload_real(tenant_a: Tenant):
    payload = json.loads(
        (SAMPLES_DIR / "aquisicao-consolidada.json").read_text(encoding="utf-8")
    )
    path = (
        f"/v2/fidc-custodia/report/aquisicao-consolidada/"
        f"{CNPJ}/{DATA_INI.isoformat()}/{DATA_FIM.isoformat()}"
    )
    transport = _build_transport(payload_by_path={path: payload})

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.custodia.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)

        step = await sync_aquisicao_consolidada(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            cnpj_fundo=CNPJ,
            data_inicial=DATA_INI,
            data_final=DATA_FIM,
        )

    assert step["ok"]
    assert step["raw_persisted"] is True
    assert step["canonical_rows_upserted"] == 583

    async with AsyncSessionLocal() as db:
        canon = (
            await db.execute(
                select(AquisicaoRecebivel).where(
                    AquisicaoRecebivel.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(canon) == 583
        # Raw gravado tambem
        raws = (
            await db.execute(
                select(QiTechRawRelatorio).where(
                    QiTechRawRelatorio.tenant_id == tenant_a.id,
                    QiTechRawRelatorio.tipo_de_mercado
                    == "fidc-custodia/aquisicao-consolidada",
                )
            )
        ).scalars().all()
        assert len(raws) == 1


@pytest.mark.asyncio
async def test_sync_liquidados_baixados_payload_real(tenant_a: Tenant):
    payload = json.loads(
        (SAMPLES_DIR / "liquidados-baixados-v2.json").read_text(encoding="utf-8")
    )
    path = (
        f"/v2/fidc-custodia/report/liquidados-baixados/v2/"
        f"{CNPJ}/{DATA_INI.isoformat()}/{DATA_FIM.isoformat()}"
    )
    transport = _build_transport(payload_by_path={path: payload})

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.custodia.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)

        step = await sync_liquidados_baixados(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            cnpj_fundo=CNPJ,
            data_inicial=DATA_INI,
            data_final=DATA_FIM,
        )

    assert step["ok"]
    assert step["canonical_rows_upserted"] == 799
    async with AsyncSessionLocal() as db:
        canon = (
            await db.execute(
                select(LiquidacaoRecebivel).where(
                    LiquidacaoRecebivel.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(canon) == 799


@pytest.mark.asyncio
async def test_sync_detalhes_operacoes_payload_real(tenant_a: Tenant):
    payload = json.loads(
        (SAMPLES_DIR / "detalhes-operacoes.json").read_text(encoding="utf-8")
    )
    data_imp = date(2026, 1, 8)
    path = f"/v2/fidc-custodia/report/fundo/{CNPJ}/data/{data_imp.isoformat()}"
    transport = _build_transport(payload_by_path={path: payload})

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.custodia.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)

        step = await sync_detalhes_operacoes(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            cnpj_fundo=CNPJ,
            data_importacao=data_imp,
        )

    assert step["ok"]
    assert step["canonical_rows_upserted"] == 5
    async with AsyncSessionLocal() as db:
        canon = (
            await db.execute(
                select(OperacaoRemessa).where(
                    OperacaoRemessa.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(canon) == 5


@pytest.mark.asyncio
async def test_sync_idempotente(tenant_a: Tenant):
    """Re-rodar com mesmo período não duplica linhas."""
    payload = json.loads(
        (SAMPLES_DIR / "aquisicao-consolidada.json").read_text(encoding="utf-8")
    )
    path = (
        f"/v2/fidc-custodia/report/aquisicao-consolidada/"
        f"{CNPJ}/{DATA_INI.isoformat()}/{DATA_FIM.isoformat()}"
    )
    transport = _build_transport(payload_by_path={path: payload})

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.custodia.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)
        await sync_aquisicao_consolidada(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            cnpj_fundo=CNPJ,
            data_inicial=DATA_INI,
            data_final=DATA_FIM,
        )
        await sync_aquisicao_consolidada(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            cnpj_fundo=CNPJ,
            data_inicial=DATA_INI,
            data_final=DATA_FIM,
        )

    async with AsyncSessionLocal() as db:
        canon = (
            await db.execute(
                select(AquisicaoRecebivel).where(
                    AquisicaoRecebivel.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(canon) == 583


@pytest.mark.asyncio
async def test_sync_isolamento_tenant(tenant_a: Tenant, tenant_b: Tenant):
    """Tenant A grava — tenant B nao ve."""
    payload = json.loads(
        (SAMPLES_DIR / "detalhes-operacoes.json").read_text(encoding="utf-8")
    )
    data_imp = date(2026, 1, 8)
    path = f"/v2/fidc-custodia/report/fundo/{CNPJ}/data/{data_imp.isoformat()}"
    transport = _build_transport(payload_by_path={path: payload})

    with patch(
        "app.modules.integracoes.adapters.admin.qitech.custodia.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)
        await sync_detalhes_operacoes(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            cnpj_fundo=CNPJ,
            data_importacao=data_imp,
        )

    async with AsyncSessionLocal() as db:
        b = (
            await db.execute(
                select(OperacaoRemessa).where(
                    OperacaoRemessa.tenant_id == tenant_b.id
                )
            )
        ).scalars().all()
        assert b == []
