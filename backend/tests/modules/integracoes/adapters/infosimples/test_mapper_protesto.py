"""Unit tests do mapper de protesto (funcoes puras, tolerantes a layout).

O payload do detalhe SP segue o exemplo real da doc Infosimples v2.2.37
(ieptb/protestos/detalhes-sp) -- onde o credor (nome_cedente/nome_apresentante)
aparece. O nacional e sintetico (estrutura cartorio -> titulo + obter_detalhes).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.integracoes.adapters.data.infosimples.mappers.protesto import (
    extract_sp_detail_requests,
    map_protesto,
)

# data[0] do exemplo real da doc (ieptb/protestos/detalhes-sp).
_SP_DETALHE = {
    "consulta_data": "11/11/1111",
    "consulta_datahora": "24/02/2023 08:40",
    "protestos": [
        {
            "cpf_cnpj": "12.345.678/9012-34",
            "data_protesto": "2018-04-12",
            "data_protesto_string": "12/04/2018",
            "data_vencimento": "11/11/1111",
            "data_vencimento_string": "",
            "valor": 26.5,
            "valor_string": "26,50",
            "chave": "111111111111",
            "nome_apresentante": "BANCO EXEMPLO S.A.",
            "nome_cedente": "FORNECEDOR EXEMPLO LTDA",
            "tem_anuencia": "Não",
        }
    ],
    "site_receipt": "https://www.exemplo.com/exemplo-de-url",
}

# Nacional sintetico: cartorios SP com token obter_detalhes + titulos sem credor.
_NACIONAL = {
    "documento": "12345678000190",
    "constam_protestos": True,
    "quantidade_titulos": 2,
    "valor_total": "1.234,56",
    "cartorios": [
        {
            "cartorio": "1 Tabeliao de Protesto",
            "cidade": "São Paulo",
            "uf": "SP",
            "obter_detalhes": "TOKEN_SP_1",
            "titulos": [{"data_protesto": "2020-01-10", "valor": "1.000,00"}],
        },
        {
            "cartorio": "2 Oficio",
            "cidade": "Campinas",
            "uf": "SP",
            "obter_detalhes": "TOKEN_SP_2",
            "titulos": [{"data_protesto": "2021-05-03", "valor": "234,56"}],
        },
    ],
}


def test_detalhe_sp_extrai_credor():
    f = map_protesto(_SP_DETALHE)
    assert f.constam_protestos is True
    assert f.qtd_total == 1
    assert f.com_credor is True
    assert len(f.titulos) == 1
    t = f.titulos[0]
    # Credor = nome_cedente (preferido sobre apresentante).
    assert t.credor == "FORNECEDOR EXEMPLO LTDA"
    assert t.valor == Decimal("26.5")
    assert t.data_protesto == date(2018, 4, 12)
    # cpf_cnpj e o SACADO (devedor), NAO o documento do credor.
    assert t.documento_credor is None
    # O response do detalhe-sp NAO repete cartorio/cidade/uf por titulo — esse
    # contexto e carregado no nivel do ProtestoParte (service _fetch_ieptb, a
    # partir do SpDetailRequest), nao injetado por titulo no mapper.
    assert t.cartorio is None
    assert t.uf is None
    # apresentante preservado no detalhe (subset escalar).
    assert t.detalhe.get("nome_apresentante") == "BANCO EXEMPLO S.A."


def test_nacional_agrega_sem_credor():
    f = map_protesto(_NACIONAL)
    assert f.constam_protestos is True
    assert f.qtd_total == 2  # explicito do header
    assert f.valor_total == Decimal("1234.56")
    assert f.com_credor is False
    assert len(f.titulos) == 2
    # Titulos herdam cartorio/uf do no ancestral.
    primeiro = next(t for t in f.titulos if t.valor == Decimal("1000.00"))
    assert primeiro.cartorio == "1 Tabeliao de Protesto"
    assert primeiro.uf == "SP"
    assert primeiro.data_protesto == date(2020, 1, 10)
    assert all(t.credor is None for t in f.titulos)


def test_extract_sp_detail_requests():
    reqs = extract_sp_detail_requests(_NACIONAL)
    tokens = {r.obter_detalhes for r in reqs}
    assert tokens == {"TOKEN_SP_1", "TOKEN_SP_2"}
    r1 = next(r for r in reqs if r.obter_detalhes == "TOKEN_SP_1")
    assert r1.cartorio == "1 Tabeliao de Protesto"
    assert r1.cidade == "São Paulo"
    assert r1.uf == "SP"


def test_sem_protestos():
    f = map_protesto({"constam_protestos": False, "quantidade_titulos": 0})
    assert f.constam_protestos is False
    assert f.qtd_total == 0
    assert f.titulos == []
    assert f.com_credor is False
    assert extract_sp_detail_requests({"constam_protestos": False}) == []
