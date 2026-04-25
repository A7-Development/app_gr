"""map_demonstrativo_caixa -- payload QiTech -> linhas wh_movimento_caixa."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_demonstrativo_caixa,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION

SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-13"
    / "demonstrativo-caixa.json"
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


def test_mapeia_15_linhas(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_demonstrativo_caixa(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert len(rows) == 15


def test_source_id_unico_mesmo_com_descricao_repetida(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    """Sample tem 2 lancamentos com mesma descricao "Resgate do Fundo
    REALINVEST VENCIDOS [REALIVEN]" e valores diferentes. UQ via sha16
    do item garante 2 linhas distintas em vez de 1 sobreposta."""
    rows = map_demonstrativo_caixa(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    source_ids = [r["source_id"] for r in rows]
    assert len(source_ids) == len(set(source_ids))  # todos unicos


def test_source_id_format(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_demonstrativo_caixa(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    for r in rows:
        # {clienteId}|{data_iso}|{sha16} -- clienteId pode ter espaco
        # ("REALINVEST MEZ", "REALINVEST SEN") mas nunca pipe.
        parts = r["source_id"].split("|")
        assert len(parts) == 3
        assert parts[0].startswith("REALINVEST")
        assert parts[1] == "2026-01-13"
        assert len(parts[2]) == 16  # sha16


def test_decimal_preserva_negativos_em_saidas(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    """Saidas vem negativas da QiTech ("-25.4", "-419375.99", etc.)."""
    rows = map_demonstrativo_caixa(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    # Pega a TARIFA DE TED (saida -25.4).
    tarifa = next(r for r in rows if "TARIFA DE TED" in r["descricao"])
    assert tarifa["saidas"] == Decimal("-25.4")
    assert tarifa["entradas"] == Decimal("0")


def test_data_liquidacao_vem_do_payload(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    """data_liquidacao parseada de `dataLiquidação`, nao do param."""
    rows = map_demonstrativo_caixa(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert all(r["data_liquidacao"] == date(2026, 1, 13) for r in rows)


def test_proveniencia(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_demonstrativo_caixa(
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


def test_dados_bancarios_null_normalizados(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    """Sample tem todos os campos bancarios null. Devem virar None."""
    rows = map_demonstrativo_caixa(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    for r in rows:
        assert r["banco"] is None
        assert r["agencia"] is None
        assert r["conta_corrente"] is None
        assert r["digito"] is None


def test_envelope_vazio(tenant_id: UUID, data_posicao: date) -> None:
    payload = {"relatórios": {}, "_links": {}, "message": "x"}
    assert (
        map_demonstrativo_caixa(
            payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
        )
        == []
    )


def test_lista_vazia(tenant_id: UUID, data_posicao: date) -> None:
    payload = {"relatórios": {"demonstrativo-caixa": []}}
    assert (
        map_demonstrativo_caixa(
            payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
        )
        == []
    )


def test_item_nao_dict_ignorado(tenant_id: UUID, data_posicao: date) -> None:
    payload = {
        "relatórios": {
            "demonstrativo-caixa": [
                None,
                {
                    "dataLiquidação": "2026-01-13T00:00:00.000Z",
                    "tipoDeRegistro": 1,
                    "descrição": "X",
                    "entradas": 100,
                    "saídas": 0,
                    "saldo": 100,
                    "históricoTraduzido": "X",
                    "idConta": 0,
                    "banco": None,
                    "agencia": None,
                    "contaCorrente": None,
                    "digito": None,
                    "contaInvestimento": None,
                    "cpfDoCliente": "00000000000000",
                    "clienteNome": "N",
                    "clienteId": "C",
                },
            ]
        }
    }
    rows = map_demonstrativo_caixa(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert len(rows) == 1
    assert rows[0]["descricao"] == "X"
