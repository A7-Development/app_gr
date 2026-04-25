"""map_cpr -- payload QiTech -> linhas wh_cpr_movimento."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.admin.qitech.mappers import map_cpr
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION

SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-13"
    / "cpr.json"
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


def test_mapeia_11_linhas(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_cpr(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
    assert len(rows) == 11


def test_decimal_preserva_negativos(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_cpr(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
    auditoria = next(r for r in rows if "Auditoria" in r["descricao"])
    # Despesa de auditoria = -7501.98
    assert auditoria["valor"] == Decimal("-7501.98")


def test_percentual_8_decimais(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    """percentualSobreCpr tem 8 casas decimais ('-0.00025545'). Numeric(12,8)."""
    rows = map_cpr(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
    selic = next(r for r in rows if "SELIC" in r["descricao"])
    assert selic["percentual_sobre_cpr"] == Decimal("-0.00025545")


def test_source_id_unico_e_format(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_cpr(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
    sids = [r["source_id"] for r in rows]
    assert len(sids) == len(set(sids))  # todos unicos
    for sid in sids:
        parts = sid.split("|")
        assert len(parts) == 3
        assert parts[0] == "REALINVEST"
        assert parts[1] == "2026-01-13"
        assert len(parts[2]) == 16


def test_proveniencia(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_cpr(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
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
    assert map_cpr(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao) == []


def test_lista_vazia(tenant_id: UUID, data_posicao: date) -> None:
    payload = {"relatórios": {"cpr": []}}
    assert map_cpr(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao) == []


def test_data_posicao_usa_param(payload: dict, tenant_id: UUID) -> None:
    rows = map_cpr(payload=payload, tenant_id=tenant_id, data_posicao=date(2026, 6, 1))
    assert all(r["data_posicao"] == date(2026, 6, 1) for r in rows)


def test_item_nao_dict_ignorado(tenant_id: UUID, data_posicao: date) -> None:
    payload = {
        "relatórios": {
            "cpr": [
                None,
                {
                    "dataDaPosição": "2026-01-13T00:00:00.000Z",
                    "descrição": "X",
                    "valor": -100,
                    "percentualSobreCpr": -0.5,
                    "percentualSobreTotal": -0.01,
                    "históricoTraduzido": "X",
                    "cpfDoCliente": "00000000000000",
                    "clienteNome": "N",
                    "clienteId": "C",
                },
            ]
        }
    }
    rows = map_cpr(payload=payload, tenant_id=tenant_id, data_posicao=data_posicao)
    assert len(rows) == 1
