"""map_tesouraria -- payload QiTech -> linhas wh_saldo_tesouraria."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.admin.qitech.mappers import map_tesouraria
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION

SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-13"
    / "tesouraria.json"
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


def test_mapeia_3_classes_de_cota(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_tesouraria(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert len(rows) == 3
    cliente_ids = {r["carteira_cliente_id"] for r in rows}
    assert cliente_ids == {"REALINVEST", "REALINVEST MEZ", "REALINVEST SEN"}


def test_decimal_e_descricao(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_tesouraria(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    by_id = {r["carteira_cliente_id"]: r for r in rows}
    assert by_id["REALINVEST"]["valor"] == Decimal("281.66")
    assert by_id["REALINVEST MEZ"]["valor"] == Decimal("0")
    assert all(r["descricao"] == "Saldo em Tesouraria" for r in rows)


def test_source_id_inclui_classe_de_cota(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_tesouraria(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    by_id = {r["carteira_cliente_id"]: r for r in rows}
    # Diferenciacao via clienteId (descricao e identica em todas).
    assert by_id["REALINVEST"]["source_id"] == "REALINVEST|2026-01-13"
    assert by_id["REALINVEST MEZ"]["source_id"] == "REALINVEST MEZ|2026-01-13"
    assert by_id["REALINVEST SEN"]["source_id"] == "REALINVEST SEN|2026-01-13"


def test_proveniencia(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_tesouraria(
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
    payload = {"relatórios": {}, "_links": {}, "message": "Não há resultados"}
    rows = map_tesouraria(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert rows == []


def test_lista_vazia(tenant_id: UUID, data_posicao: date) -> None:
    payload = {"relatórios": {"tesouraria": []}}
    rows = map_tesouraria(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert rows == []


def test_data_posicao_usa_param(payload: dict, tenant_id: UUID) -> None:
    rows = map_tesouraria(
        payload=payload, tenant_id=tenant_id, data_posicao=date(2026, 2, 1)
    )
    assert all(r["source_id"].endswith("|2026-02-01") for r in rows)


def test_item_nao_dict_ignorado(tenant_id: UUID, data_posicao: date) -> None:
    payload = {
        "relatórios": {
            "tesouraria": [
                None,
                {
                    "dataDaPosição": "2026-01-13T00:00:00.000Z",
                    "descrição": "X",
                    "valor": 100,
                    "percentualSobreCpr": 50,
                    "percentualSobreTotal": 1,
                    "cpfDoCliente": "00000000000000",
                    "clienteNome": "N",
                    "clienteId": "C",
                },
            ]
        }
    }
    rows = map_tesouraria(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert len(rows) == 1
    assert rows[0]["carteira_cliente_id"] == "C"
