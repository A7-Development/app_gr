"""map_conta_corrente -- contrato payload QiTech -> linhas canonicas.

Fixture: sample real qitech_samples/a7-credit/2026-01-13/conta-corrente.json
(3 contas REALINVEST: BRADESCO, CONCILIA, SOCOPA).
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
    map_conta_corrente,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION

SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-13"
    / "conta-corrente.json"
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


def test_mapeia_todas_as_3_contas(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_conta_corrente(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert len(rows) == 3
    codigos = {r["codigo"] for r in rows}
    assert codigos == {"BRADESCO", "CONCILIA", "SOCOPA"}


def test_decimal_precision(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_conta_corrente(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    by_code = {r["codigo"]: r for r in rows}
    assert by_code["BRADESCO"]["valor_total"] == Decimal("13671.59")
    # Saldo negativo (creditos a conciliar) preservado.
    assert by_code["CONCILIA"]["valor_total"] == Decimal("-80310.61")
    assert by_code["SOCOPA"]["valor_total"] == Decimal("66639.02")
    assert by_code["CONCILIA"]["percentual_sobre_total"] == Decimal("-0.76")


def test_source_id_determinista(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_conta_corrente(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    by_code = {r["codigo"]: r for r in rows}
    assert by_code["BRADESCO"]["source_id"] == "REALINVEST|BRADESCO|2026-01-13"
    assert by_code["SOCOPA"]["source_id"] == "REALINVEST|SOCOPA|2026-01-13"


def test_dimensoes(payload: dict, tenant_id: UUID, data_posicao: date) -> None:
    rows = map_conta_corrente(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert all(r["carteira_cliente_id"] == "REALINVEST" for r in rows)
    assert all(r["carteira_cliente_doc"] == "42449234000160" for r in rows)
    by_code = {r["codigo"]: r for r in rows}
    assert by_code["BRADESCO"]["instituicao"] == "BRADESCO"
    assert by_code["SOCOPA"]["instituicao"] == "SINGCTVM"
    assert by_code["CONCILIA"]["descricao"] == "CREDITOS A CONCILIAR"


def test_proveniencia(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_conta_corrente(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    expected_updated = datetime(2026, 1, 13, 0, 0, 0, tzinfo=UTC)
    for r in rows:
        assert r["tenant_id"] == tenant_id
        assert r["data_posicao"] == data_posicao
        assert r["source_type"] == SourceType.ADMIN_QITECH
        assert r["trust_level"] == TrustLevel.HIGH
        assert r["ingested_by_version"] == ADAPTER_VERSION
        assert r["collected_by"] is None
        assert r["source_updated_at"] == expected_updated
        assert isinstance(r["hash_origem"], str)
        assert len(r["hash_origem"]) == 64
        assert isinstance(r["ingested_at"], datetime)
        assert r["ingested_at"].tzinfo is not None


def test_hashes_distintos(payload: dict, tenant_id: UUID, data_posicao: date) -> None:
    rows = map_conta_corrente(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    hashes = {r["hash_origem"] for r in rows}
    assert len(hashes) == 3


def test_envelope_vazio_retorna_lista_vazia(
    tenant_id: UUID, data_posicao: date
) -> None:
    payload = {
        "relatórios": {},
        "_links": {},
        "message": "Não há resultados para os parâmetros informados.",
    }
    rows = map_conta_corrente(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert rows == []


def test_lista_vazia_retorna_lista_vazia(
    tenant_id: UUID, data_posicao: date
) -> None:
    payload = {"relatórios": {"conta-corrente": []}}
    rows = map_conta_corrente(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert rows == []


def test_payload_sem_chave_relatorios(
    tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_conta_corrente(
        payload={"outra_coisa": 1}, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert rows == []


def test_data_posicao_usa_param(
    payload: dict, tenant_id: UUID
) -> None:
    rows = map_conta_corrente(
        payload=payload, tenant_id=tenant_id, data_posicao=date(2026, 1, 14)
    )
    assert all(r["data_posicao"] == date(2026, 1, 14) for r in rows)
    assert all(r["source_id"].endswith("|2026-01-14") for r in rows)


def test_item_nao_dict_e_ignorado(
    tenant_id: UUID, data_posicao: date
) -> None:
    payload = {
        "relatórios": {
            "conta-corrente": [
                None,
                "lixo",
                {
                    "dataDaPosição": "2026-01-13T00:00:00.000Z",
                    "código": "BANCO",
                    "descrição": "D",
                    "instituição": "I",
                    "valorTotal": 100,
                    "percentualSobreContaCorrente": 50,
                    "percentualSobreTotal": 1,
                    "cpfDoCliente": "00000000000000",
                    "clienteNome": "N",
                    "clienteId": "C",
                },
            ]
        }
    }
    rows = map_conta_corrente(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert len(rows) == 1
    assert rows[0]["codigo"] == "BANCO"
