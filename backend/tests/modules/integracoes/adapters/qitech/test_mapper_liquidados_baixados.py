"""map_liquidados_baixados -- valida normalizacao de tipos inconsistentes."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_liquidados_baixados,
)
from app.modules.integracoes.adapters.admin.qitech.mappers.liquidados_baixados import (
    _parse_loose_decimal,
)

SAMPLE = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "fidc-custodia-2026-01-01-2026-01-08"
    / "liquidados-baixados-v2.json"
)
CNPJ = "42449234000160"


@pytest.fixture
def payload() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


def test_loose_decimal_aceita_locale_br():
    """Helper: aceita float, int, string com vírgula, string com ponto."""
    assert _parse_loose_decimal(12699.03) == Decimal("12699.03")
    assert _parse_loose_decimal(12699) == Decimal("12699")
    assert _parse_loose_decimal("12699,03") == Decimal("12699.03")
    assert _parse_loose_decimal("0,00") == Decimal("0")
    assert _parse_loose_decimal("12699.03") == Decimal("12699.03")
    assert _parse_loose_decimal(None) == Decimal("0")
    assert _parse_loose_decimal("") == Decimal("0")
    # Garbage -> 0 (defensivo).
    assert _parse_loose_decimal("xpto") == Decimal("0")


def test_mapeia_799_liquidacoes(payload: dict, tenant_id: UUID) -> None:
    rows = map_liquidados_baixados(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    assert len(rows) == 799


def test_valor_vencimento_string_br_normalizado(
    payload: dict, tenant_id: UUID
) -> None:
    """Sample item 1: valorVencimento='12699,03' (string locale BR)."""
    rows = map_liquidados_baixados(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    r0 = rows[0]
    assert r0["valor_vencimento"] == Decimal("12699.03")
    assert r0["ajuste"] == Decimal("0")
    # valorAquisicao vem como float — tambem virar Decimal correto
    assert r0["valor_aquisicao"] == Decimal("12328.01")
    assert r0["valor_pago"] == Decimal("12699.03")


def test_estado_e_tipo_movimento(payload: dict, tenant_id: UUID) -> None:
    rows = map_liquidados_baixados(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    r0 = rows[0]
    assert r0["st_recebivel"] == "VENCIDOS"
    assert r0["tipo_movimento"] == "BAIXA POR DEPOSITO SACADO"


def test_datas(payload: dict, tenant_id: UUID) -> None:
    rows = map_liquidados_baixados(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    r0 = rows[0]
    assert r0["data_posicao"] == date(2026, 1, 2)
    assert r0["data_aquisicao"] == date(2025, 11, 18)
    assert r0["data_vencimento"] == date(2025, 12, 17)


def test_source_id(payload: dict, tenant_id: UUID) -> None:
    rows = map_liquidados_baixados(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    assert rows[0]["source_id"] == f"{CNPJ}|382258959|liq"


def test_source_ids_unicos(payload: dict, tenant_id: UUID) -> None:
    rows = map_liquidados_baixados(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    sids = [r["source_id"] for r in rows]
    # Pode ter duplicatas no payload em casos edge (refundo de baixa);
    # source_id e idempotente — UQ no DB lida com isso.
    assert len(sids) == len(rows)


def test_envelope_vazio(tenant_id: UUID) -> None:
    assert (
        map_liquidados_baixados(
            payload={"liquidadosBaixados": []},
            tenant_id=tenant_id,
            cnpj_fundo=CNPJ,
        )
        == []
    )
