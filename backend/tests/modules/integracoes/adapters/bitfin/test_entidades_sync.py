"""Unit tests — mapper do party model (entidades_sync, sem DB).

Cobre o contrato do mapper Entidade->wh_entidade: identidade derivada
(documento/raiz/filial/matriz), campos cadastrais e proveniencia Auditable
completa. A decisao de quarentena (doc None/invalido) e coberta pelos testes
de app/shared/documento.py.
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.core.enums import SourceType, TipoPessoa, TrustLevel
from app.modules.integracoes.adapters.erp.bitfin.entidades_sync import _map_entidade
from app.modules.integracoes.adapters.erp.bitfin.version import ADAPTER_VERSION
from app.shared.documento import normalizar_documento

TENANT = uuid4()


def _row_bitfin_pj() -> dict:
    """Linha como SELECT_ENTIDADE_FULL devolve (PJ, padded 15)."""
    return {
        "entidade_id": 4321,
        "tipo": "PJ",
        "documento": "011444777000161",  # padded a 15, raiz 11444777 matriz
        "nome": "  Exemplo Industria LTDA  ",
        "cnae_chave": "1011-2/01",
        "cnae_denominacao": "Frigorifico - abate de bovinos",
        "porte": "ME",
        "data_constituicao": datetime(2010, 3, 1, tzinfo=UTC),
        "em_recuperacao_judicial": False,
        "data_recuperacao_judicial": None,
        "logradouro": "Rua das Flores",
        "endereco_numero": "100",
        "complemento": None,
        "bairro": "Centro",
        "localidade": "Sao Paulo",
        "estado": "SP",
        "cep": "01310100",
        "pais": "Brasil",
        "endereco_verificado": True,
        "grupo_economico_source_id": 77,
        "data_cadastro_fonte": datetime(2020, 1, 15, tzinfo=UTC),
    }


def test_map_entidade_identidade_e_cadastro():
    row = _row_bitfin_pj()
    doc = normalizar_documento(row["documento"], TipoPessoa.PJ)
    assert doc is not None and doc.valido

    mapped = _map_entidade(row, TENANT, doc)

    assert mapped["tenant_id"] == TENANT
    assert mapped["documento"] == "11444777000161"
    assert mapped["tipo_pessoa"] == TipoPessoa.PJ
    assert mapped["documento_raiz"] == "11444777"
    assert mapped["filial_numero"] == "0001"
    assert mapped["is_matriz"] is True
    assert mapped["nome"] == "Exemplo Industria LTDA"  # trimmed
    assert mapped["cnae_chave"] == "1011-2/01"
    assert mapped["grupo_economico_source_id"] == 77
    assert mapped["estado"] == "SP"


def test_map_entidade_proveniencia_completa():
    row = _row_bitfin_pj()
    doc = normalizar_documento(row["documento"], TipoPessoa.PJ)
    assert doc is not None

    mapped = _map_entidade(row, TENANT, doc)

    assert mapped["source_type"] == SourceType.ERP_BITFIN
    assert mapped["source_id"] == "4321"
    assert mapped["source_updated_at"] == row["data_cadastro_fonte"]
    assert mapped["ingested_by_version"] == ADAPTER_VERSION
    assert mapped["trust_level"] == TrustLevel.HIGH
    assert mapped["hash_origem"]  # sha256 presente


def test_map_entidade_nome_vazio_e_cep_vazio_viram_placeholder_e_none():
    row = _row_bitfin_pj()
    row["nome"] = "   "
    row["cep"] = " "
    doc = normalizar_documento(row["documento"], TipoPessoa.PJ)
    assert doc is not None

    mapped = _map_entidade(row, TENANT, doc)

    assert mapped["nome"] == "(sem nome)"
    assert mapped["cep"] is None
