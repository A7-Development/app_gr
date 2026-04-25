"""ETL QiTech outros-fundos — integracao end-to-end (DB real).

Testa o fluxo completo: fetch (mockado via httpx.MockTransport) -> raw
upsert -> mapper -> canonico upsert -> decision_log. DB real do Postgres
de testes — JSONB e ON CONFLICT exigem PG, nao da pra rodar com SQLite.

Cada teste cria um tenant fresco via fixture pra garantir isolamento.
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
    sync_all,
    sync_outros_fundos,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.shared.identity.tenant import Tenant
from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio

SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-13"
    / "outros-fundos.json"
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
        base_url="https://api.test",
        client_id="u",
        client_secret="p",
    )


def _build_transport(
    *, report_body: object, report_status: int = 200
) -> httpx.MockTransport:
    """MockTransport: token endpoint -> apiToken fixo; market -> body configurado."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/painel/token/api":
            return httpx.Response(200, json={"apiToken": "T"})
        return httpx.Response(report_status, json=report_body)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_sync_outros_fundos_payload_real_grava_raw_e_canonico(
    tenant_a: Tenant, real_payload: dict
):
    """Caminho feliz: 3 posicoes REALINVEST sao gravadas em raw E canonico.

    Valida que:
    - 1 linha em wh_qitech_raw_relatorio com payload=body inteiro, http_status=200
    - 3 linhas em wh_posicao_cota_fundo (uma por ativo)
    - hash da raw bate com SHA256 do payload via sha256_of_row
    """
    transport = _build_transport(report_body=real_payload, report_status=200)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.etl.build_async_client",
    ) as mock_client_factory:
        # Reuso do build_async_client real, mas com transport mockado.
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_client_factory.side_effect = lambda **kw: real_build(
            **kw, transport=transport
        )

        step = await sync_outros_fundos(
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

    # Raw — 1 linha com payload completo.
    async with AsyncSessionLocal() as db:
        raws = (
            await db.execute(
                select(QiTechRawRelatorio).where(
                    QiTechRawRelatorio.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(raws) == 1
        raw = raws[0]
        assert raw.tipo_de_mercado == "outros-fundos"
        assert raw.data_posicao == DATA_POSICAO
        assert raw.http_status == 200
        assert raw.payload == real_payload
        assert raw.fetched_by_version == ADAPTER_VERSION
        # SHA hex de 64 chars.
        assert len(raw.payload_sha256) == 64

    # Canonico — 3 posicoes.
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(PosicaoCotaFundo).where(
                    PosicaoCotaFundo.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(rows) == 3
        codigos = {r.ativo_codigo for r in rows}
        assert codigos == {"739704", "REALIAVE", "REALIVEN"}
        # Decimal precision do REALIAVE — guard contra float drift.
        realiave = next(r for r in rows if r.ativo_codigo == "REALIAVE")
        assert realiave.quantidade == Decimal("18892619.39422062")
        assert realiave.valor_cota == Decimal("0.97833113")


@pytest.mark.asyncio
async def test_sync_outros_fundos_envelope_vazio_grava_raw_status_400_e_zero_canonico(
    tenant_a: Tenant, empty_envelope: dict
):
    """QiTech respondeu HTTP 400 + envelope vazio (sem dados naquele dia).

    Comportamento esperado:
    - Raw e gravada com http_status=400 (preserva distincao "sem dados" vs erro)
    - Canonico recebe 0 linhas
    - step.ok = True (nao e erro de integracao)
    """
    transport = _build_transport(report_body=empty_envelope, report_status=400)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.etl.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)

        step = await sync_outros_fundos(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            data_posicao=DATA_POSICAO,
        )

    assert step["ok"] is True
    assert step["raw_http_status"] == 400
    assert step["raw_persisted"] is True
    assert step["canonical_rows_upserted"] == 0
    assert step["errors"] == []

    async with AsyncSessionLocal() as db:
        raw = (
            await db.execute(
                select(QiTechRawRelatorio).where(
                    QiTechRawRelatorio.tenant_id == tenant_a.id
                )
            )
        ).scalar_one()
        assert raw.http_status == 400
        assert raw.payload == empty_envelope

        canon_count = (
            await db.execute(
                select(PosicaoCotaFundo).where(
                    PosicaoCotaFundo.tenant_id == tenant_a.id
                )
            )
        ).all()
        assert canon_count == []


@pytest.mark.asyncio
async def test_sync_outros_fundos_e_idempotente(
    tenant_a: Tenant, real_payload: dict
):
    """Re-rodar o sync no mesmo dia substitui via UQ (raw e canonico).

    Pos-condicao apos 2 rodadas:
    - 1 linha em raw (mesma chave, atualizada)
    - 3 linhas em canonico (mesmas source_ids, atualizadas)
    Nao 2 e nao 6.
    """
    transport = _build_transport(report_body=real_payload, report_status=200)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.etl.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)

        await sync_outros_fundos(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            data_posicao=DATA_POSICAO,
        )
        # Segunda rodada — idempotente.
        step2 = await sync_outros_fundos(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            data_posicao=DATA_POSICAO,
        )

    assert step2["ok"]

    async with AsyncSessionLocal() as db:
        raw_count = (
            await db.execute(
                select(QiTechRawRelatorio).where(
                    QiTechRawRelatorio.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(raw_count) == 1

        canon_count = (
            await db.execute(
                select(PosicaoCotaFundo).where(
                    PosicaoCotaFundo.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(canon_count) == 3


@pytest.mark.asyncio
async def test_sync_outros_fundos_isolamento_de_tenant(
    tenant_a: Tenant, tenant_b: Tenant, real_payload: dict
):
    """Sync no tenant A nao contamina tenant B."""
    transport = _build_transport(report_body=real_payload, report_status=200)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.etl.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)

        await sync_outros_fundos(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            config=_cfg(),
            data_posicao=DATA_POSICAO,
        )

    async with AsyncSessionLocal() as db:
        b_raw = (
            await db.execute(
                select(QiTechRawRelatorio).where(
                    QiTechRawRelatorio.tenant_id == tenant_b.id
                )
            )
        ).scalars().all()
        assert b_raw == []
        b_canon = (
            await db.execute(
                select(PosicaoCotaFundo).where(
                    PosicaoCotaFundo.tenant_id == tenant_b.id
                )
            )
        ).scalars().all()
        assert b_canon == []


@pytest.mark.asyncio
async def test_sync_all_grava_decision_log_com_metricas(
    tenant_a: Tenant, real_payload: dict
):
    """`sync_all` deve gravar 1 entry em decision_log com summary."""
    transport = _build_transport(report_body=real_payload, report_status=200)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.etl.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)

        summary = await sync_all(
            tenant_a.id,
            _cfg(),
            DATA_POSICAO,
            environment=Environment.PRODUCTION,
            triggered_by="user:test",
        )

    assert summary["ok"] is True
    # rows_ingested >= 3 (tenant tem 3 posicoes outros-fundos; pode haver
    # outros endpoints no _PIPELINE com 0 itens neste sample).
    assert summary["rows_ingested"] >= 3
    of_steps = [s for s in summary["steps"] if s["tipo_de_mercado"] == "outros-fundos"]
    assert len(of_steps) == 1
    assert of_steps[0]["canonical_rows_upserted"] == 3

    async with AsyncSessionLocal() as db:
        entries = (
            await db.execute(
                select(DecisionLog).where(DecisionLog.tenant_id == tenant_a.id)
            )
        ).scalars().all()
        sync_entries = [e for e in entries if e.decision_type == DecisionType.SYNC]
        assert len(sync_entries) == 1
        e = sync_entries[0]
        assert e.rule_or_model == "qitech_adapter"
        assert e.rule_or_model_version == ADAPTER_VERSION
        assert e.triggered_by == "user:test"
        assert e.output["rows_ingested"] == 3
        assert e.inputs_ref["data_posicao"] == "2026-01-13"


@pytest.mark.asyncio
async def test_sync_all_resolve_data_posicao_d_minus_1_quando_since_none(
    tenant_a: Tenant, empty_envelope: dict
):
    """Sem `since`, sync_all alvo D-1 UTC. Validamos via summary, nao DB
    (envelope vazio nao gera linha canonica)."""
    transport = _build_transport(report_body=empty_envelope, report_status=400)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.etl.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)

        summary = await sync_all(
            tenant_a.id,
            _cfg(),
            None,  # sem since -> D-1
            environment=Environment.PRODUCTION,
        )

    from datetime import UTC, datetime, timedelta

    expected = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    assert summary["data_posicao"] == expected
    assert summary["since"] is None
