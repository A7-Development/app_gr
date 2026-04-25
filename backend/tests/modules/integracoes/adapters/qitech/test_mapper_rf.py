"""map_rf -- payload QiTech -> linhas wh_posicao_renda_fixa."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.admin.qitech.mappers import map_rf
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION

SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-13"
    / "rf.json"
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


def test_mapeia_26_titulos(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_rf(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
    assert len(rows) == 26


def test_indexadores_observados(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_rf(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
    indexadores = {r["indexador"] for r in rows}
    assert indexadores == {"CDI", "IPCA", "PRE"}


def test_decimal_precision_taxas(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_rf(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
    # Primeiro item: C274830 (CDI MEZAN). taxaOver = 2.348072088015352.
    by_code = {r["codigo"]: r for r in rows}
    c274830 = by_code["C274830"]
    assert c274830["taxa_over"] == Decimal("2.348072088015352")
    assert c274830["taxa_ano"] == Decimal("6.000000000000005")
    assert c274830["quantidade"] == Decimal("-685.59531")  # negativo (resgate)
    assert c274830["pu_mercado"] == Decimal("1118.37975508")
    assert c274830["valor_bruto"] == Decimal("-766755.91")  # negativo


def test_datas_parseadas(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_rf(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
    by_code = {r["codigo"]: r for r in rows}
    c274830 = by_code["C274830"]
    assert c274830["data_aplicacao"] == date(2025, 6, 23)
    assert c274830["data_da_emissao"] == date(2025, 6, 23)
    assert c274830["data_vencimento"] == date(2049, 12, 31)
    assert c274830["data_vencimento_lastro"] == date(2049, 12, 31)


def test_ntn_b_indexador_ipca(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_rf(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
    ntn_b = next(r for r in rows if r["nome_do_papel"] == "NTN-B")
    assert ntn_b["indexador"] == "IPCA"
    assert ntn_b["emitente"] == "STNC"
    assert ntn_b["cnpj_emitente"] == "00394460040950"


def test_source_id(payload: dict, tenant_id: UUID, data_posicao: date) -> None:
    rows = map_rf(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
    by_code = {r["codigo"]: r for r in rows}
    assert by_code["C274830"]["source_id"] == "REALINVEST|C274830|2026-01-13"
    assert by_code["B811154"]["source_id"] == "REALINVEST|B811154|2026-01-13"


def test_mtm_null_normalizado(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    """Sample tem `mtm: null` em todos. Deve virar None."""
    rows = map_rf(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
    assert all(r["mtm"] is None for r in rows)


def test_proveniencia(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_rf(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
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
    assert map_rf(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao) == []


def test_lista_vazia(tenant_id: UUID, data_posicao: date) -> None:
    payload = {"relatórios": {"rf": []}}
    assert map_rf(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao) == []


def test_data_posicao_usa_param(payload: dict, tenant_id: UUID) -> None:
    rows = map_rf(payload=payload, tenant_id=tenant_id, data_posicao=date(2026, 9, 1))
    assert all(r["data_posicao"] == date(2026, 9, 1) for r in rows)
    assert all(r["source_id"].endswith("|2026-09-01") for r in rows)
