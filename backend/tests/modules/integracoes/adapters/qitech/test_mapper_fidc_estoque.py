"""map_fidc_estoque -- CSV QiTech -> linhas wh_estoque_recebivel.

Fixture: CSV real baixado do S3 da QiTech (job 908aaf59-... de 2026-04-25)
para o REALINVEST FIDC com data de referencia 2026-01-08. 2390 recebiveis.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_fidc_estoque,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION

SAMPLE_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-08"
    / "fidc-estoque.csv"
)


@pytest.fixture
def csv_text() -> str:
    return SAMPLE_PATH.read_text(encoding="utf-8")


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def data_referencia() -> date:
    return date(2026, 1, 8)


def test_mapeia_2390_recebiveis(
    csv_text: str, tenant_id: UUID, data_referencia: date
) -> None:
    """Sample tem 2391 linhas (1 header + 2390 dados)."""
    rows = map_fidc_estoque(
        csv_text=csv_text, tenant_id=tenant_id, data_referencia=data_referencia
    )
    assert len(rows) == 2390


def test_cnpj_normalizado_sem_pontuacao(
    csv_text: str, tenant_id: UUID, data_referencia: date
) -> None:
    """CSV traz '42.449.234/0001-60' — esperamos so digitos."""
    rows = map_fidc_estoque(
        csv_text=csv_text, tenant_id=tenant_id, data_referencia=data_referencia
    )
    r0 = rows[0]
    assert r0["fundo_doc"] == "42449234000160"
    assert r0["fundo_nome"] == "REALINVEST FIDC"
    assert r0["gestor_doc"] == "45934845000192"
    assert r0["gestor_nome"] == "Onboard Consultoria Ltda"


def test_decimal_locale_br(
    csv_text: str, tenant_id: UUID, data_referencia: date
) -> None:
    """'3600,00' (CSV BR) -> Decimal('3600.00')."""
    rows = map_fidc_estoque(
        csv_text=csv_text, tenant_id=tenant_id, data_referencia=data_referencia
    )
    r0 = rows[0]
    assert r0["valor_nominal"] == Decimal("3600.00")
    assert r0["valor_presente"] == Decimal("3534.91")
    assert r0["valor_aquisicao"] == Decimal("3461.26")
    assert r0["valor_pdd"] == Decimal("0.00")
    # Taxa com 10 decimais.
    assert r0["taxa_cessao"] == Decimal("0.4692739943")
    assert r0["taxa_recebivel"] == Decimal("0.4243427048")


def test_data_locale_br(
    csv_text: str, tenant_id: UUID, data_referencia: date
) -> None:
    """'08/01/2026' -> date(2026, 1, 8)."""
    rows = map_fidc_estoque(
        csv_text=csv_text, tenant_id=tenant_id, data_referencia=data_referencia
    )
    r0 = rows[0]
    # CSV col 21 (dataVencimentoOriginal) = 27/01/2026
    assert r0["data_vencimento_original"] == date(2026, 1, 27)
    assert r0["data_vencimento_ajustada"] == date(2026, 1, 27)
    assert r0["data_emissao"] == date(2025, 12, 15)
    assert r0["data_aquisicao"] == date(2025, 12, 16)
    # data_fundo no sample = '24/04/2026' (primeira linha).
    assert r0["data_fundo"] == date(2026, 4, 24)


def test_coobrigacao_bool(
    csv_text: str, tenant_id: UUID, data_referencia: date
) -> None:
    """'SIM' -> True."""
    rows = map_fidc_estoque(
        csv_text=csv_text, tenant_id=tenant_id, data_referencia=data_referencia
    )
    # Sample: primeira linha tem coobrigacao SIM.
    assert rows[0]["coobrigacao"] is True


def test_situacao_e_faixa_pdd(
    csv_text: str, tenant_id: UUID, data_referencia: date
) -> None:
    rows = map_fidc_estoque(
        csv_text=csv_text, tenant_id=tenant_id, data_referencia=data_referencia
    )
    r0 = rows[0]
    assert r0["situacao_recebivel"] == "A Vencer"
    assert r0["faixa_pdd"] == "A"
    assert r0["tipo_recebivel"] == "Duplicata"


def test_source_id_format(
    csv_text: str, tenant_id: UUID, data_referencia: date
) -> None:
    rows = map_fidc_estoque(
        csv_text=csv_text, tenant_id=tenant_id, data_referencia=data_referencia
    )
    r0 = rows[0]
    # {docFundo}|{docCedente}|{seuNumero}|{numeroDocumento}|{data_iso}
    expected = "42449234000160|24987496000105|DID76860|2598/3|2026-01-08"
    assert r0["source_id"] == expected


def test_source_ids_distintos(
    csv_text: str, tenant_id: UUID, data_referencia: date
) -> None:
    """2390 source_ids -- todos unicos (UQ no warehouse)."""
    rows = map_fidc_estoque(
        csv_text=csv_text, tenant_id=tenant_id, data_referencia=data_referencia
    )
    sids = [r["source_id"] for r in rows]
    assert len(sids) == len(set(sids))


def test_proveniencia(
    csv_text: str, tenant_id: UUID, data_referencia: date
) -> None:
    rows = map_fidc_estoque(
        csv_text=csv_text, tenant_id=tenant_id, data_referencia=data_referencia
    )
    for r in rows[:10]:  # amostra
        assert r["tenant_id"] == tenant_id
        assert r["data_referencia"] == data_referencia
        assert r["source_type"] == SourceType.ADMIN_QITECH
        assert r["trust_level"] == TrustLevel.HIGH
        assert r["ingested_by_version"] == ADAPTER_VERSION
        assert r["collected_by"] is None
        assert isinstance(r["hash_origem"], str)
        assert len(r["hash_origem"]) == 64


def test_hashes_distintos(
    csv_text: str, tenant_id: UUID, data_referencia: date
) -> None:
    rows = map_fidc_estoque(
        csv_text=csv_text, tenant_id=tenant_id, data_referencia=data_referencia
    )
    # Hashes podem repetir se 2 linhas forem byte-identicas (improvavel
    # mas possivel). Tirar amostra grande e verificar cardinalidade > 99%.
    hashes = {r["hash_origem"] for r in rows}
    assert len(hashes) >= int(len(rows) * 0.99)


def test_csv_vazio_retorna_lista_vazia(
    tenant_id: UUID, data_referencia: date
) -> None:
    assert (
        map_fidc_estoque(
            csv_text="", tenant_id=tenant_id, data_referencia=data_referencia
        )
        == []
    )


def test_csv_so_header_retorna_lista_vazia(
    tenant_id: UUID, data_referencia: date
) -> None:
    header_only = (
        "nomeFundo;docFundo;dataFundo;nomeGestor;docGestor;nomeOriginador;"
        "docOriginador;nomeCedente;docCedente;nomeSacado;docSacado;seuNumero;"
        "numeroDocumento;tipoRecebivel;valorNominal;valorPresente;valorAquisicao;"
        "valorPdd;faixaPdd;dataReferencia;dataVencimentoOriginal;"
        "dataVencimentoAjustada;dataEmissao;dataAquisicao;prazo;prazoAnual;"
        "situacaoRecebivel;taxaCessao;taxaRecebivel;coobrigacao\n"
    )
    rows = map_fidc_estoque(
        csv_text=header_only,
        tenant_id=tenant_id,
        data_referencia=data_referencia,
    )
    assert rows == []


def test_data_referencia_usa_param(csv_text: str, tenant_id: UUID) -> None:
    """data_referencia vem do PARAM, nao do CSV — pra idempotencia."""
    rows = map_fidc_estoque(
        csv_text=csv_text,
        tenant_id=tenant_id,
        data_referencia=date(2026, 12, 31),
    )
    assert all(r["data_referencia"] == date(2026, 12, 31) for r in rows[:5])
    assert all(r["source_id"].endswith("|2026-12-31") for r in rows[:5])


def test_decimal_zero_em_valor_pdd(
    csv_text: str, tenant_id: UUID, data_referencia: date
) -> None:
    """Faixa A no sample = sem PDD = '0,00'."""
    rows = map_fidc_estoque(
        csv_text=csv_text, tenant_id=tenant_id, data_referencia=data_referencia
    )
    faixa_a = [r for r in rows if r["faixa_pdd"] == "A"]
    assert len(faixa_a) > 0
    # Em A, PDD esperado e zero (regulacao Bacen 2682).
    assert all(r["valor_pdd"] == Decimal("0.00") for r in faixa_a[:50])
