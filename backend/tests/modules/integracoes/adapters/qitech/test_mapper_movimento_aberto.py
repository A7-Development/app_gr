"""map_movimento_aberto -- snapshot atual de cessoes em aberto.

Sample real veio vazio em 2026-04-25 — fixture sintetica baseada na spec
fornecida pelo user. Quando aparecer dado real, atualizar fixture.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.core.enums import SourceType
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_movimento_aberto,
)

CNPJ = "42449234000160"


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def data_referencia() -> date:
    return date(2026, 4, 25)


@pytest.fixture
def payload_sintetico() -> dict:
    """Schema baseado em spec passada pelo user (2026-04-25)."""
    return {
        "movimentoAberto": [
            {
                "nomeFundo": "REALINVEST FIDC",
                "docFundo": 42449234000160,
                "dataMovimento": "2026-04-25T00:00:00.000Z",
                "seuNumero": 12345,  # spec diz integer
                "numeroDocumento": "DOC-001",
                "tipoMovimento": "AQUISICAO",
                "dataVencimento": "2026-05-25T00:00:00.000Z",
                "valorAquisicao": 1000.50,
                "valorNominal": 1100,
                "valorMovimentacao": 1000.50,
            },
            {
                "nomeFundo": "REALINVEST FIDC",
                "docFundo": 42449234000160,
                "dataMovimento": "2026-04-24T00:00:00.000Z",
                "seuNumero": 12346,
                "numeroDocumento": "DOC-002",
                "tipoMovimento": "AQUISICAO",
                "dataVencimento": "2026-05-30T00:00:00.000Z",
                "valorAquisicao": 2500.00,
                "valorNominal": 2700,
                "valorMovimentacao": 2500.00,
            },
        ]
    }


def test_mapeia_2_movimentos(
    payload_sintetico: dict, tenant_id: UUID, data_referencia: date
) -> None:
    rows = map_movimento_aberto(
        payload=payload_sintetico,
        tenant_id=tenant_id,
        cnpj_fundo=CNPJ,
        data_referencia=data_referencia,
    )
    assert len(rows) == 2


def test_seu_numero_int_vira_string(
    payload_sintetico: dict, tenant_id: UUID, data_referencia: date
) -> None:
    rows = map_movimento_aberto(
        payload=payload_sintetico,
        tenant_id=tenant_id,
        cnpj_fundo=CNPJ,
        data_referencia=data_referencia,
    )
    assert rows[0]["seu_numero"] == "12345"
    assert isinstance(rows[0]["seu_numero"], str)


def test_doc_fundo_int_normalizado(
    payload_sintetico: dict, tenant_id: UUID, data_referencia: date
) -> None:
    rows = map_movimento_aberto(
        payload=payload_sintetico,
        tenant_id=tenant_id,
        cnpj_fundo=CNPJ,
        data_referencia=data_referencia,
    )
    assert rows[0]["fundo_doc"] == CNPJ


def test_decimais(
    payload_sintetico: dict, tenant_id: UUID, data_referencia: date
) -> None:
    rows = map_movimento_aberto(
        payload=payload_sintetico,
        tenant_id=tenant_id,
        cnpj_fundo=CNPJ,
        data_referencia=data_referencia,
    )
    r0 = rows[0]
    assert r0["valor_aquisicao"] == Decimal("1000.50")
    assert r0["valor_nominal"] == Decimal("1100")
    assert r0["valor_movimentacao"] == Decimal("1000.50")


def test_datas(
    payload_sintetico: dict, tenant_id: UUID, data_referencia: date
) -> None:
    rows = map_movimento_aberto(
        payload=payload_sintetico,
        tenant_id=tenant_id,
        cnpj_fundo=CNPJ,
        data_referencia=data_referencia,
    )
    r0 = rows[0]
    assert r0["data_referencia"] == data_referencia
    assert r0["data_movimento"] == date(2026, 4, 25)
    assert r0["data_vencimento"] == date(2026, 5, 25)


def test_source_id_inclui_data_referencia(
    payload_sintetico: dict, tenant_id: UUID, data_referencia: date
) -> None:
    """source_id inclui data_referencia (snapshot diferente = chave diferente)."""
    rows = map_movimento_aberto(
        payload=payload_sintetico,
        tenant_id=tenant_id,
        cnpj_fundo=CNPJ,
        data_referencia=data_referencia,
    )
    expected = f"{CNPJ}|12345|DOC-001|abt|2026-04-25"
    assert rows[0]["source_id"] == expected


def test_source_ids_mesma_cessao_em_dias_diferentes_diferem(
    payload_sintetico: dict, tenant_id: UUID
) -> None:
    """Mesma cessao em snapshots diferentes -> source_ids distintos
    (cada dia preserva sua foto)."""
    rows_d1 = map_movimento_aberto(
        payload=payload_sintetico,
        tenant_id=tenant_id,
        cnpj_fundo=CNPJ,
        data_referencia=date(2026, 4, 25),
    )
    rows_d2 = map_movimento_aberto(
        payload=payload_sintetico,
        tenant_id=tenant_id,
        cnpj_fundo=CNPJ,
        data_referencia=date(2026, 4, 26),
    )
    assert rows_d1[0]["source_id"] != rows_d2[0]["source_id"]


def test_proveniencia(
    payload_sintetico: dict, tenant_id: UUID, data_referencia: date
) -> None:
    rows = map_movimento_aberto(
        payload=payload_sintetico,
        tenant_id=tenant_id,
        cnpj_fundo=CNPJ,
        data_referencia=data_referencia,
    )
    for r in rows:
        assert r["tenant_id"] == tenant_id
        assert r["source_type"] == SourceType.ADMIN_QITECH


def test_envelope_vazio(tenant_id: UUID, data_referencia: date) -> None:
    """Sample real do REALINVEST veio assim — confirmar comportamento."""
    rows = map_movimento_aberto(
        payload={"movimentoAberto": []},
        tenant_id=tenant_id,
        cnpj_fundo=CNPJ,
        data_referencia=data_referencia,
    )
    assert rows == []
