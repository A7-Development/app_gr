"""map_detalhes_operacoes -- payload lista direta -> wh_operacao_remessa."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_detalhes_operacoes,
)

SAMPLE = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "fidc-custodia-2026-01-01-2026-01-08"
    / "detalhes-operacoes.json"
)
CNPJ = "42449234000160"


@pytest.fixture
def payload() -> list:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


def test_mapeia_5_operacoes(payload: list, tenant_id: UUID) -> None:
    rows = map_detalhes_operacoes(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    assert len(rows) == 5


def test_id_operacao_e_arquivo(payload: list, tenant_id: UUID) -> None:
    rows = map_detalhes_operacoes(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    r0 = rows[0]
    assert r0["id_operacao_recebivel"] == "8784306"
    assert r0["nome_arquivo"] == "42449234000160_001.rem"
    assert r0["nome_arquivo_entrada"] == "429_1.rem"


def test_decimais_e_data(payload: list, tenant_id: UUID) -> None:
    rows = map_detalhes_operacoes(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    r0 = rows[0]
    assert r0["remessa"] == Decimal("58398.53")
    assert r0["valor_total"] == Decimal("58398.53")
    assert r0["reembolso"] == Decimal("0")
    assert r0["recompra"] == Decimal("0")
    assert r0["data_importacao"] == date(2026, 1, 8)


def test_coobrigacao_sim_vira_true(payload: list, tenant_id: UUID) -> None:
    rows = map_detalhes_operacoes(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    # Sample tem coobrigacao=SIM em todas — todas True.
    assert all(r["coobrigacao"] is True for r in rows)


def test_source_id(payload: list, tenant_id: UUID) -> None:
    rows = map_detalhes_operacoes(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    assert rows[0]["source_id"] == f"{CNPJ}|8784306|rem"


def test_source_ids_unicos(payload: list, tenant_id: UUID) -> None:
    rows = map_detalhes_operacoes(
        payload=payload, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    sids = [r["source_id"] for r in rows]
    assert len(sids) == len(set(sids))


def test_aceita_payload_wrapped_defensivo(tenant_id: UUID) -> None:
    """Se a QiTech um dia mudar pra wrapper, mapper aceita."""
    body = {
        "detalhesOperacoes": [
            {
                "idOperacaoRecebivel": 1,
                "nomeFundo": "X",
                "cnpjFundo": "00000000000000",
                "gestor": "G",
                "cnpjGestor": "00000000000000",
                "nomeCedente": "C",
                "documentoCedente": "00000000000000",
                "nomeArquivo": "a.rem",
                "nomeArquivoEntrada": "a.rem",
                "data": "2026-01-08T00:00:00.000Z",
                "remessa": 100,
                "reembolso": 0,
                "recompra": 0,
                "valorTotal": 100,
                "coobrigacao": "SIM",
                "tipoRecebivel": "Duplicata",
            }
        ]
    }
    rows = map_detalhes_operacoes(
        payload=body, tenant_id=tenant_id, cnpj_fundo=CNPJ
    )
    assert len(rows) == 1


def test_lista_vazia(tenant_id: UUID) -> None:
    assert (
        map_detalhes_operacoes(payload=[], tenant_id=tenant_id, cnpj_fundo=CNPJ)
        == []
    )
