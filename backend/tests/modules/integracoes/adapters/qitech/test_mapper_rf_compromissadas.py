"""map_rf_compromissadas -- payload QiTech -> linhas wh_posicao_compromissada.

Sample real do probe (2026-04-07): 1 NTN O overnight do REALINVEST FIDC.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_rf_compromissadas,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION

SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-04-07"
    / "rf-compromissadas.json"
)


@pytest.fixture
def payload() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def data_posicao() -> date:
    return date(2026, 4, 7)


def test_mapeia_compromissada(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_rf_compromissadas(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["codigo"] == "C398038"
    assert r["papel"] == "NTN O"
    assert r["data_aquisicao"] == date(2026, 4, 6)
    assert r["data_resgate"] == date(2026, 4, 7)
    assert r["taxa_ano"] == Decimal("14.05")
    assert r["valor_resgate"] == Decimal("22430.49")


def test_source_id(payload: dict, tenant_id: UUID, data_posicao: date) -> None:
    rows = map_rf_compromissadas(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert rows[0]["source_id"] == "REALINVEST|C398038|2026-04-07"


def test_proveniencia(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_rf_compromissadas(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    expected = datetime(2026, 4, 7, 0, 0, 0, tzinfo=UTC)
    r = rows[0]
    assert r["tenant_id"] == tenant_id
    assert r["source_type"] == SourceType.ADMIN_QITECH
    assert r["trust_level"] == TrustLevel.HIGH
    assert r["ingested_by_version"] == ADAPTER_VERSION
    assert r["source_updated_at"] == expected
    assert r["mtm"] is None  # null no sample
    assert r["negociacao_vencimento"] is None


def test_envelope_vazio(tenant_id: UUID) -> None:
    payload = {"relatórios": {}, "_links": {}, "message": "x"}
    assert (
        map_rf_compromissadas(
            payload=payload, tenant_id=tenant_id, data_posicao=date(2026, 1, 1)
        )
        == []
    )


def test_lista_vazia(tenant_id: UUID) -> None:
    payload = {"relatórios": {"rf-compromissadas": []}}
    assert (
        map_rf_compromissadas(
            payload=payload, tenant_id=tenant_id, data_posicao=date(2026, 1, 1)
        )
        == []
    )


def test_data_posicao_usa_param(payload: dict, tenant_id: UUID) -> None:
    rows = map_rf_compromissadas(
        payload=payload, tenant_id=tenant_id, data_posicao=date(2026, 12, 31)
    )
    assert all(r["data_posicao"] == date(2026, 12, 31) for r in rows)
    assert all(r["source_id"].endswith("|2026-12-31") for r in rows)
