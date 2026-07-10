"""Testes do ETL SERPRO -- bronze wh_serpro_raw_nfe (dedup + isolamento §10.4)."""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.data.serpro.client import SerproNfeResponse
from app.modules.integracoes.adapters.data.serpro.etl import persistir_snapshot
from app.shared.audit_log.decision_log import DecisionLog
from app.shared.identity.tenant import Tenant
from app.warehouse.serpro_raw_nfe import SerproRawNfe

CHAVE = "35220241522703000167550010000001211000225472"


def _response(text: str | None = None, *, qtd_eventos: int = 1) -> SerproNfeResponse:
    body = {
        "nfeProc": {"protNFe": {"infProt": {"cStat": 100}}},
        "procEventoNFe": [{"evento": {}}] * qtd_eventos or None,
    }
    raw_text = text if text is not None else json.dumps(body)
    return SerproNfeResponse(
        chave=CHAVE,
        raw=json.loads(raw_text),
        text=raw_text,
        http_status=200,
        latency_ms=10.0,
        request_tag="test",
    )


@pytest.mark.asyncio
async def test_persiste_snapshot_e_decision_log(tenant_a: Tenant) -> None:
    async with AsyncSessionLocal() as db:
        result = await persistir_snapshot(
            db, tenant_id=tenant_a.id, response=_response(), trigger="bancada"
        )
        await db.commit()

    assert result.changed is True
    assert result.cstat == 100
    assert result.qtd_eventos == 1

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                sa.select(SerproRawNfe).where(SerproRawNfe.id == result.raw_id)
            )
        ).scalar_one()
        assert row.tenant_id == tenant_a.id
        assert row.chave_acesso == CHAVE
        assert row.trigger == "bancada"
        assert row.payload["nfeProc"]["protNFe"]["infProt"]["cStat"] == 100

        log = (
            await db.execute(
                sa.select(DecisionLog).where(
                    DecisionLog.tenant_id == tenant_a.id,
                    DecisionLog.rule_or_model == "serpro_adapter",
                )
            )
        ).scalars().all()
        assert len(log) == 1
        assert log[0].output["changed"] is True


@pytest.mark.asyncio
async def test_dedup_payload_identico_nao_duplica(tenant_a: Tenant) -> None:
    async with AsyncSessionLocal() as db:
        r1 = await persistir_snapshot(
            db, tenant_id=tenant_a.id, response=_response(), trigger="bancada"
        )
        r2 = await persistir_snapshot(
            db, tenant_id=tenant_a.id, response=_response(), trigger="sweep"
        )
        await db.commit()

    assert r1.changed is True
    assert r2.changed is False
    assert r2.raw_id == r1.raw_id  # dedup casa a linha existente

    async with AsyncSessionLocal() as db:
        count = (
            await db.execute(
                sa.select(sa.func.count()).select_from(SerproRawNfe).where(
                    SerproRawNfe.tenant_id == tenant_a.id
                )
            )
        ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_estado_novo_gera_segunda_linha(tenant_a: Tenant) -> None:
    async with AsyncSessionLocal() as db:
        r1 = await persistir_snapshot(
            db, tenant_id=tenant_a.id, response=_response(qtd_eventos=1),
            trigger="bancada",
        )
        # Evento novo chegou -> payload diferente -> snapshot novo.
        r2 = await persistir_snapshot(
            db, tenant_id=tenant_a.id, response=_response(qtd_eventos=2),
            trigger="webhook",
        )
        await db.commit()

    assert r1.changed and r2.changed
    assert r1.raw_id != r2.raw_id


@pytest.mark.asyncio
async def test_isolamento_tenant(tenant_a: Tenant, tenant_b: Tenant) -> None:
    """§10.4: mesmo payload em tenants distintos = linhas independentes;

    leitura escopada de B nao ve dado de A."""
    async with AsyncSessionLocal() as db:
        ra = await persistir_snapshot(
            db, tenant_id=tenant_a.id, response=_response(), trigger="bancada"
        )
        rb = await persistir_snapshot(
            db, tenant_id=tenant_b.id, response=_response(), trigger="bancada"
        )
        await db.commit()

    assert ra.raw_id != rb.raw_id
    assert ra.changed and rb.changed  # dedup NAO cruza tenants

    async with AsyncSessionLocal() as db:
        rows_b = (
            await db.execute(
                sa.select(SerproRawNfe.id).where(
                    SerproRawNfe.tenant_id == tenant_b.id
                )
            )
        ).scalars().all()
    assert rows_b == [rb.raw_id]
