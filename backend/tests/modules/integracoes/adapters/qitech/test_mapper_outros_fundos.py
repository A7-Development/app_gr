"""map_outros_fundos — contrato payload QiTech -> linhas canonicas.

Usa como fixture o sample real capturado em producao
(qitech_samples/a7-credit/2026-01-13/outros-fundos.json), garantindo que o
mapper continua alinhado com o payload que a QiTech realmente devolve — nao
com uma mock idealizada.
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
    map_outros_fundos,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION

# Sample real do tenant a7-credit no dia 2026-01-13 — 3 posicoes do
# REALINVEST FIDC (ITAU SOBERANO + REALINVEST A VENCER + REALINVEST VENCIDOS).
SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-13"
    / "outros-fundos.json"
)


@pytest.fixture
def payload() -> dict:
    assert SAMPLE_PATH.exists(), f"Sample nao encontrado em {SAMPLE_PATH}"
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def data_posicao() -> date:
    return date(2026, 1, 13)


def test_mapeia_todas_as_posicoes_do_sample(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_outros_fundos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert len(rows) == 3
    codigos = {r["ativo_codigo"] for r in rows}
    assert codigos == {"739704", "REALIAVE", "REALIVEN"}


def test_decimal_precision_preservada(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    """Observado no sample: quantidades com 8 casas decimais e cotas com 8
    casas. Qualquer round-trip float -> Decimal quebra o teste.
    """
    rows = map_outros_fundos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    by_code = {r["ativo_codigo"]: r for r in rows}

    # REALINVEST A VENCER — quantidade com 8 decimais.
    assert by_code["REALIAVE"]["quantidade"] == Decimal("18892619.39422062")
    assert by_code["REALIAVE"]["valor_cota"] == Decimal("0.97833113")
    assert by_code["REALIAVE"]["valor_atual"] == Decimal("18483237.68")
    assert by_code["REALIAVE"]["percentual_sobre_total"] == Decimal("175.64")

    # ITAU — cota com 6 decimais.
    assert by_code["739704"]["valor_cota"] == Decimal("82.140195")
    assert by_code["739704"]["quantidade"] == Decimal("5290.61362737")


def test_source_id_composto_e_determinista(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_outros_fundos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    by_code = {r["ativo_codigo"]: r for r in rows}

    assert by_code["739704"]["source_id"] == "REALINVEST|739704|2026-01-13"
    assert by_code["REALIAVE"]["source_id"] == "REALINVEST|REALIAVE|2026-01-13"
    assert by_code["REALIVEN"]["source_id"] == "REALINVEST|REALIVEN|2026-01-13"


def test_dimensoes_carteira_e_ativo(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_outros_fundos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    # Todas as 3 posicoes sao do mesmo cliente-carteira.
    assert all(r["carteira_cliente_id"] == "REALINVEST" for r in rows)
    assert all(r["carteira_cliente_nome"] == "REALINVEST FIDC" for r in rows)
    # cpfDoCliente e na verdade CNPJ (14 digitos) — nome historico da QiTech.
    assert all(r["carteira_cliente_doc"] == "42449234000160" for r in rows)

    by_code = {r["ativo_codigo"]: r for r in rows}
    assert by_code["739704"]["ativo_nome"] == "ITAU SOBERANO REF SI"
    assert by_code["739704"]["ativo_instituicao"] == "ITAU"
    assert by_code["REALIAVE"]["ativo_instituicao"] == "SOC"


def test_sac_normaliza_vazio_e_null_para_none(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    """Sample tem os 3 casos reais:
    - `codigoDoClienteNoSAC: ""` (ITAU) -> None
    - `codigoDoClienteNoSAC: null` (REALIAVE, REALIVEN) -> None
    """
    rows = map_outros_fundos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert all(r["carteira_cliente_sac"] is None for r in rows)


def test_source_updated_at_parseia_iso_com_z(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_outros_fundos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    expected = datetime(2026, 1, 13, 0, 0, 0, tzinfo=UTC)
    assert all(r["source_updated_at"] == expected for r in rows)


def test_proveniencia_preenchida_em_todas_as_linhas(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    rows = map_outros_fundos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    for r in rows:
        assert r["tenant_id"] == tenant_id
        assert r["data_posicao"] == data_posicao
        assert r["source_type"] == SourceType.ADMIN_QITECH
        assert r["trust_level"] == TrustLevel.HIGH
        assert r["ingested_by_version"] == ADAPTER_VERSION
        assert r["collected_by"] is None
        # hash_origem e SHA256 em hex -> 64 chars.
        assert isinstance(r["hash_origem"], str)
        assert len(r["hash_origem"]) == 64
        # ingested_at foi setado pelo mapper (datetime com tz).
        assert isinstance(r["ingested_at"], datetime)
        assert r["ingested_at"].tzinfo is not None


def test_hash_origem_difere_entre_posicoes(
    payload: dict, tenant_id: UUID, data_posicao: date
) -> None:
    """Cada posicao tem hash distinto — garante que `hash_origem` reflete
    conteudo da linha, nao apenas o fundo.
    """
    rows = map_outros_fundos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    hashes = {r["hash_origem"] for r in rows}
    assert len(hashes) == 3


def test_envelope_vazio_retorna_lista_vazia(
    tenant_id: UUID, data_posicao: date
) -> None:
    """QiTech devolve `{"relatórios": {}, "message": ...}` quando nao ha
    dados. Mapper NAO pode falhar — retorna [] para o ETL registrar
    "dia sem posicoes" (diferente de "falha de integracao").
    """
    payload = {
        "relatórios": {},
        "_links": {},
        "message": "Não há resultados para os parâmetros informados.",
    }
    rows = map_outros_fundos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert rows == []


def test_lista_de_outros_fundos_vazia_retorna_lista_vazia(
    tenant_id: UUID, data_posicao: date
) -> None:
    payload = {"relatórios": {"outros-fundos": []}}
    rows = map_outros_fundos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert rows == []


def test_payload_sem_chave_relatorios_retorna_vazio(
    tenant_id: UUID, data_posicao: date
) -> None:
    """Defensivo — se QiTech algum dia devolver shape diferente, mapper
    degrada pra [] em vez de estourar."""
    rows = map_outros_fundos(
        payload={"outra_coisa": 1}, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert rows == []

    rows = map_outros_fundos(
        payload={"relatórios": []}, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert rows == []


def test_data_posicao_usa_param_nao_o_payload(
    payload: dict, tenant_id: UUID
) -> None:
    """Se QiTech drift-a TZ e devolve 2026-01-12T23:00:00Z, o mapper usa a
    data passada pelo ETL (fonte da verdade pra particionamento)."""
    mapped = map_outros_fundos(
        payload=payload, tenant_id=tenant_id, data_posicao=date(2026, 1, 14)
    )
    assert all(r["data_posicao"] == date(2026, 1, 14) for r in mapped)
    # source_id carrega a data do param — estabilidade do upsert.
    assert all(r["source_id"].endswith("|2026-01-14") for r in mapped)


def test_item_nao_dict_e_ignorado(
    tenant_id: UUID, data_posicao: date
) -> None:
    """Payload heterogeneo (nunca observado, mas defensivo): itens nao-dict
    sao skippados em vez de quebrar o sync inteiro."""
    payload = {
        "relatórios": {
            "outros-fundos": [
                "sujeira",
                None,
                {
                    "dataDaPosição": "2026-01-13T00:00:00.000Z",
                    "código": "X",
                    "fundo": "F",
                    "nomeDaInstituição": "I",
                    "quantidade": 1,
                    "quantidadeBloqueada": 0,
                    "valorDaCota": 1,
                    "valorAplicação/resgate": 0,
                    "valorAtual": 1,
                    "valorDeImpostos": 0,
                    "valorLíquido": 1,
                    "percentualSobreFundos": 100,
                    "percentualSobreTotal": 100,
                    "códigoDoClienteNoSAC": None,
                    "cpfDoCliente": "00000000000000",
                    "clienteNome": "N",
                    "clienteId": "C",
                },
            ]
        }
    }
    rows = map_outros_fundos(
        payload=payload, tenant_id=tenant_id, data_posicao=data_posicao
    )
    assert len(rows) == 1
    assert rows[0]["ativo_codigo"] == "X"
