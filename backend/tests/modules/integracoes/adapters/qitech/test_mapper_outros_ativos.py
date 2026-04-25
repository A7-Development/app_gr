"""map_outros_ativos -- payload QiTech -> linhas wh_posicao_outros_ativos."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_outros_ativos,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION

SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-13"
    / "outros-ativos.json"
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


def test_mapeia_pdd(payload: dict, tenant_id: UUID, data_posicao: date) -> None:
    """Sample tem 1 linha: PDD -2696.31.50."""
    rows = map_outros_ativos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert len(rows) == 1
    pdd = rows[0]
    assert pdd["codigo"] == "PDD"
    assert pdd["descricao"] == "PDD-Prov.Dev.Duvidos"
    # PDD reduz ativo (negativo).
    assert pdd["valor_total"] == Decimal("-269631.5")
    assert pdd["tipo_do_ativo"] == "OU"
    assert pdd["descricao_tipo_de_ativo"] == "Outros"


def test_source_id(payload: dict, tenant_id: UUID, data_posicao: date) -> None:
    rows = map_outros_ativos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert rows[0]["source_id"] == "REALINVEST|PDD|2026-01-13"


def test_proveniencia(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_outros_ativos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    r = rows[0]
    assert r["tenant_id"] == tenant_id
    assert r["source_type"] == SourceType.ADMIN_QITECH
    assert r["trust_level"] == TrustLevel.HIGH
    assert r["ingested_by_version"] == ADAPTER_VERSION
    assert r["source_updated_at"] == datetime(2026, 1, 13, 0, 0, 0, tzinfo=UTC)
    assert len(r["hash_origem"]) == 64


def test_envelope_vazio(tenant_id: UUID, data_posicao: date) -> None:
    payload = {"relatórios": {}, "_links": {}, "message": "x"}
    assert (
        map_outros_ativos(
            payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
        )
        == []
    )


def test_lista_vazia(tenant_id: UUID, data_posicao: date) -> None:
    payload = {"relatórios": {"outros-ativos": []}}
    assert (
        map_outros_ativos(
            payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
        )
        == []
    )


def test_data_posicao_usa_param(payload: dict, tenant_id: UUID) -> None:
    rows = map_outros_ativos(
        payload=payload, tenant_id=tenant_id, data_posicao=date(2026, 5, 1)
    )
    assert all(r["source_id"].endswith("|2026-05-01") for r in rows)


def test_item_nao_dict_ignorado(tenant_id: UUID, data_posicao: date) -> None:
    payload = {
        "relatórios": {
            "outros-ativos": [
                "lixo",
                {
                    "dataDaPosição": "2026-01-13T00:00:00.000Z",
                    "código": "X",
                    "descrição": "D",
                    "valorTotal": 1,
                    "percentualSobreOutrosAtivos": 100,
                    "percentualSobreTotal": 0,
                    "tipoDoAtivo": "OU",
                    "descriçãoTipoDeAtivo": "Outros",
                    "cpfDoCliente": "00000000000000",
                    "clienteNome": "N",
                    "clienteId": "C",
                },
            ]
        }
    }
    rows = map_outros_ativos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert len(rows) == 1
    assert rows[0]["codigo"] == "X"
