"""map_bank_account_statement -- contrato payload REAL QiTech -> linhas canonicas.

Shape observado em prod 2026-05 (payload_shapes/bank_account.statement.md):
envelope {"extrato": [...]}, sinal em `tipoLancamento` (C/D/S), `valor` sempre
positivo, `historico` = objeto {codigo, descricao}, doc da contraparte em
`inscricao` (int), linhas de saldo com `tipoLancamento="S"` e contraparte "null".
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_bank_account_statement,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def ua_id() -> UUID:
    return uuid4()


@pytest.fixture
def payload() -> dict:
    """3 movimentos (C, D, D-sem-contraparte) + 1 saldo (S)."""
    return {
        "extrato": [
            {
                "data": "2026-05-26T00:00:00.000",
                "dataHora": "26/05/2026 07:15:08",
                "valor": 1559348.82,
                "documento": 0,
                "lancamento": 50957269,
                "historico": {
                    "codigo": "0497",
                    "descricao": "TED - STR FORNECEDOR EXEMPLO LTDA",
                },
                "contraparte": {
                    "nome": "FORNECEDOR EXEMPLO LTDA",
                    "inscricao": 42449234000160,
                    "tipoPessoa": "J",
                    "indicadorEnviadoRecebido": "R",
                },
                "tipoLancamento": "C",
            },
            {
                "data": "2026-05-12T00:00:00.000",
                "dataHora": "12/05/2026 10:39:38",
                "valor": 667065.09,
                "documento": None,
                "lancamento": 50633207,
                "historico": {
                    "codigo": "0123",
                    "descricao": "TRANSFERENCIA  A DEBITO REALINVEST",
                },
                "contraparte": {
                    "nome": None,
                    "inscricao": None,
                    "tipoPessoa": None,
                    "indicadorEnviadoRecebido": None,
                },
                "tipoLancamento": "D",
            },
            {
                "data": "2026-05-15T00:00:00.000",
                "dataHora": "15/05/2026 09:22:27",
                "valor": 5556.89,
                "lancamento": 50760545,
                "historico": {"codigo": "0497", "descricao": "TED - STR PESSOA FISICA"},
                "contraparte": {
                    "nome": "JOAO DA SILVA",
                    "inscricao": 12345678901,
                    "tipoPessoa": "F",
                },
                "tipoLancamento": "D",
            },
            {
                "data": "2026-05-08T00:00:00.000",
                "dataHora": "08/05/2026 00:00:00",
                "valor": 2461.57,
                "lancamento": 24554012,
                "historico": {"codigo": "0099", "descricao": "SALDO C/C"},
                "contraparte": {"nome": "null", "inscricao": None, "tipoPessoa": "null"},
                "tipoLancamento": "S",
            },
        ]
    }


def _map(payload: dict, tenant_id: UUID, ua_id: UUID):
    return map_bank_account_statement(
        payload=payload,
        tenant_id=tenant_id,
        unidade_administrativa_id=ua_id,
        agencia="0001",
        conta="4532551",
    )


def test_descarta_linha_de_saldo(payload, tenant_id, ua_id) -> None:
    # 4 itens no payload, mas o saldo (S) e descartado -> 3 movimentos.
    rows = _map(payload, tenant_id, ua_id)
    assert len(rows) == 3
    assert all(r["tipo"] in ("C", "D") for r in rows)


def test_sinal_vem_de_tipo_lancamento_valor_positivo(payload, tenant_id, ua_id) -> None:
    rows = _map(payload, tenant_id, ua_id)
    by_lanc = {r["source_id"].split("|")[-1]: r for r in rows}
    credito = by_lanc["50957269"]
    debito = by_lanc["50633207"]
    assert credito["tipo"] == "C"
    assert debito["tipo"] == "D"
    # valor sempre positivo no warehouse (sinal vive em `tipo`).
    assert credito["valor"] == Decimal("1559348.82")
    assert debito["valor"] == Decimal("667065.09")
    assert all(r["valor"] > 0 for r in rows)


def test_historico_objeto_split_codigo_e_descricao(payload, tenant_id, ua_id) -> None:
    rows = _map(payload, tenant_id, ua_id)
    credito = next(r for r in rows if r["source_id"].endswith("50957269"))
    # codigo de historico -> coluna historico; texto -> coluna descricao.
    assert credito["historico"] == "0497"
    assert credito["descricao"] == "TED - STR FORNECEDOR EXEMPLO LTDA"


def test_contraparte_doc_zfill_por_tipo_pessoa(payload, tenant_id, ua_id) -> None:
    rows = _map(payload, tenant_id, ua_id)
    pj = next(r for r in rows if r["source_id"].endswith("50957269"))
    pf = next(r for r in rows if r["source_id"].endswith("50760545"))
    assert pj["contrapartida_doc"] == "42449234000160"  # CNPJ 14 digitos
    assert pj["contrapartida_nome"] == "FORNECEDOR EXEMPLO LTDA"
    assert pf["contrapartida_doc"] == "12345678901"  # CPF 11 digitos
    assert pf["contrapartida_nome"] == "JOAO DA SILVA"


def test_contraparte_ausente_vira_none(payload, tenant_id, ua_id) -> None:
    rows = _map(payload, tenant_id, ua_id)
    debito = next(r for r in rows if r["source_id"].endswith("50633207"))
    assert debito["contrapartida_nome"] is None
    assert debito["contrapartida_doc"] is None


def test_data_movimento_de_datahora(payload, tenant_id, ua_id) -> None:
    rows = _map(payload, tenant_id, ua_id)
    credito = next(r for r in rows if r["source_id"].endswith("50957269"))
    assert credito["data_lancamento"] == date(2026, 5, 26)
    assert credito["data_movimento"] == date(2026, 5, 26)


def test_source_id_usa_lancamento(payload, tenant_id, ua_id) -> None:
    rows = _map(payload, tenant_id, ua_id)
    credito = next(r for r in rows if r["tipo"] == "C")
    assert credito["source_id"] == (
        f"bank_account_statement|{ua_id}|0001|4532551|2026-05-26|50957269"
    )


def test_proveniencia(payload, tenant_id, ua_id) -> None:
    rows = _map(payload, tenant_id, ua_id)
    for r in rows:
        assert r["tenant_id"] == tenant_id
        assert r["source_type"] == SourceType.ADMIN_QITECH
        assert r["trust_level"] == TrustLevel.HIGH
        assert r["ingested_by_version"] == ADAPTER_VERSION
        assert r["moeda"] == "BRL"
        assert isinstance(r["hash_origem"], str) and len(r["hash_origem"]) == 64
        assert isinstance(r["ingested_at"], datetime)
    # source_updated_at vem do dataHora (timestamp do evento).
    credito = next(r for r in rows if r["tipo"] == "C")
    assert credito["source_updated_at"] == datetime(2026, 5, 26, 7, 15, 8)


def test_envelope_vazio(tenant_id, ua_id) -> None:
    assert _map({"extrato": []}, tenant_id, ua_id) == []
    assert _map({"outra_coisa": 1}, tenant_id, ua_id) == []


def test_saldo_nao_confunde_saida(tenant_id, ua_id) -> None:
    # "SAIDA" (começa com S) NAO pode virar saldo — deve ser debito.
    payload = {
        "extrato": [
            {
                "data": "2026-05-01T00:00:00.000",
                "valor": 100.0,
                "lancamento": 1,
                "historico": {"codigo": "X", "descricao": "PAGAMENTO"},
                "tipoLancamento": "SAIDA",
            }
        ]
    }
    rows = _map(payload, tenant_id, ua_id)
    assert len(rows) == 1
    assert rows[0]["tipo"] == "D"
