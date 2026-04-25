"""map_rentabilidade -- payload QiTech -> linhas wh_rentabilidade_fundo."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_rentabilidade,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION

SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-13"
    / "rentabilidade.json"
)


@pytest.fixture
def payload() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def data_posicao() -> date:
    return date(2026, 1, 13)


def test_mapeia_27_linhas(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    """3 classes x 9 indexadores = 27 linhas."""
    rows = map_rentabilidade(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert len(rows) == 27


def test_indexadores(payload: dict, tenant_id: UUID, data_posicao: date) -> None:
    rows = map_rentabilidade(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    indexadores = {r["indexador"] for r in rows}
    assert "PATRIMON" in indexadores
    assert "COTA" in indexadores
    assert "CDI" in indexadores
    assert "DOL" in indexadores


def test_patrimon_so_tem_valor_patrimonio(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    """Indexador PATRIMON: so `valor_patrimonio` preenchido; demais NULL."""
    rows = map_rentabilidade(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    patrimon = [r for r in rows if r["indexador"] == "PATRIMON"]
    assert len(patrimon) == 3  # 3 classes de cota
    for r in patrimon:
        assert r["valor_patrimonio"] is not None
        # Demais rentabilidades nulls.
        assert r["rentabilidade_diaria"] is None
        assert r["rentabilidade_anual"] is None
        assert r["percentual_bench_mark"] is None


def test_cota_tem_rentabilidades_nao_percentual(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_rentabilidade(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    cota = [
        r for r in rows
        if r["indexador"] == "COTA" and r["carteira_cliente_id"] == "REALINVEST"
    ]
    assert len(cota) == 1
    r = cota[0]
    assert r["rentabilidade_diaria"] == Decimal("0.2343556")
    assert r["rentabilidade_mensal"] == Decimal("1.6600983")
    # COTA nao tem percentualBenchMark.
    assert r["percentual_bench_mark"] is None
    # COTA nao tem valor_patrimonio.
    assert r["valor_patrimonio"] is None


def test_cdi_tem_percentual_bench_mark(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_rentabilidade(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    cdi = [
        r for r in rows
        if r["indexador"] == "CDI" and r["carteira_cliente_id"] == "REALINVEST"
    ]
    assert len(cdi) == 1
    r = cdi[0]
    assert r["percentual_bench_mark"] == Decimal("425.0880392")
    assert r["rentabilidade_real"] == Decimal("0.1791257")


def test_source_id(payload: dict, tenant_id: UUID, data_posicao: date) -> None:
    rows = map_rentabilidade(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    cdi_realinvest = next(
        r for r in rows
        if r["indexador"] == "CDI" and r["carteira_cliente_id"] == "REALINVEST"
    )
    assert cdi_realinvest["source_id"] == "REALINVEST|CDI|2026-01-13"


def test_proveniencia(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_rentabilidade(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    expected = datetime(2026, 1, 13, 0, 0, 0, tzinfo=UTC)
    for r in rows:
        assert r["tenant_id"] == tenant_id
        assert r["source_type"] == SourceType.ADMIN_QITECH
        assert r["trust_level"] == TrustLevel.HIGH
        assert r["ingested_by_version"] == ADAPTER_VERSION
        assert r["source_updated_at"] == expected
        assert len(r["hash_origem"]) == 64


def test_envelope_vazio(tenant_id: UUID, data_posicao: date) -> None:
    payload = {"relatórios": {}, "_links": {}, "message": "x"}
    assert (
        map_rentabilidade(
            payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
        )
        == []
    )


def test_lista_vazia(tenant_id: UUID, data_posicao: date) -> None:
    payload = {"relatórios": {"rentabilidade": []}}
    assert (
        map_rentabilidade(
            payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
        )
        == []
    )


def test_data_posicao_usa_param(payload: dict, tenant_id: UUID) -> None:
    rows = map_rentabilidade(
        payload=payload, tenant_id=tenant_id, data_posicao=date(2026, 8, 1)
    )
    assert all(r["data_posicao"] == date(2026, 8, 1) for r in rows)
    assert all("|2026-08-01" in r["source_id"] for r in rows)
