"""map_aquisicao_consolidada -- payload QiTech -> linhas wh_aquisicao_recebivel."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_aquisicao_consolidada,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION

SAMPLE = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "fidc-custodia-2026-01-01-2026-01-08"
    / "aquisicao-consolidada.json"
)
CNPJ = "42449234000160"


@pytest.fixture
def payload() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


def test_mapeia_583_aquisicoes(payload: dict, tenant_id: UUID) -> None:
    rows = map_aquisicao_consolidada(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    assert len(rows) == 583


def test_decimais_precisao(payload: dict, tenant_id: UUID) -> None:
    rows = map_aquisicao_consolidada(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    r0 = rows[0]
    # Sample item 1: valorCompra=155783, valorVencimento=166997, taxa=0.7930165297
    assert r0["valor_compra"] == Decimal("155783")
    assert r0["valor_vencimento"] == Decimal("166997")
    assert r0["taxa_aquisicao"] == Decimal("0.7930165297")
    assert r0["prazo_recebivel"] == 30


def test_cnpjs_normalizados_pra_string(payload: dict, tenant_id: UUID) -> None:
    """fundoCnpj vem como int, cpfCnpjCedente/Sacado como int — todos viram
    string com 14 digitos zero-pad."""
    rows = map_aquisicao_consolidada(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    r0 = rows[0]
    assert r0["fundo_doc"] == CNPJ
    assert r0["cedente_doc"] == "71923304000179"
    assert r0["sacado_doc"] == "42021022000188"


def test_id_recebivel_int_vira_string(
    payload: dict, tenant_id: UUID
) -> None:
    rows = map_aquisicao_consolidada(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    r0 = rows[0]
    assert r0["id_recebivel"] == "391759322"
    assert isinstance(r0["id_recebivel"], str)


def test_source_id(payload: dict, tenant_id: UUID) -> None:
    rows = map_aquisicao_consolidada(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    assert rows[0]["source_id"] == f"{CNPJ}|391759322|aq"


def test_source_ids_unicos(payload: dict, tenant_id: UUID) -> None:
    rows = map_aquisicao_consolidada(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    sids = [r["source_id"] for r in rows]
    assert len(sids) == len(set(sids))


def test_datas(payload: dict, tenant_id: UUID) -> None:
    rows = map_aquisicao_consolidada(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    r0 = rows[0]
    assert r0["data_aquisicao"] == date(2026, 1, 6)
    assert r0["data_vencimento"] == date(2026, 2, 19)


def test_proveniencia(payload: dict, tenant_id: UUID) -> None:
    rows = map_aquisicao_consolidada(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    for r in rows[:5]:
        assert r["tenant_id"] == tenant_id
        assert r["source_type"] == SourceType.ADMIN_QITECH
        assert r["trust_level"] == TrustLevel.HIGH
        assert r["ingested_by_version"] == ADAPTER_VERSION


def test_envelope_vazio(tenant_id: UUID) -> None:
    assert (
        map_aquisicao_consolidada(
            payload={"aquisicaoConsolidada": []},
            tenant_id=tenant_id,
            cnpj_fundo=CNPJ,
        )
        == []
    )


def test_payload_sem_wrapper_retorna_vazio(tenant_id: UUID) -> None:
    assert (
        map_aquisicao_consolidada(
            payload={"outra": []}, tenant_id=tenant_id, cnpj_fundo=CNPJ
        )
        == []
    )
