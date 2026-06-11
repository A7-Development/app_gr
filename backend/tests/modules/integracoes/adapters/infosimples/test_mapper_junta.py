"""Unit tests do mapper JUCESP (funções puras, tolerantes a layout)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.integracoes.adapters.data.infosimples.mappers.junta import (
    fields_to_jsonable,
    map_ficha,
)

_PAYLOAD = {
    "nire": "35.222.333.444",
    "nome": "ACME COMERCIO LTDA",
    "objeto_social": "Comercio de pecas",
    "autenticidade": "ABC123",
    "empresa": {
        "cnpj": "12.345.678/0001-90",
        "tipo": "LTDA",
        "data_constituicao": "30/01/2006",
        "inicio_atividades": "2006-02-01",
        "inscricao_estadual": "123.456.789.000",
    },
    "capital": {"valor": "R$ 500.000,00", "texto": "quinhentos mil reais"},
    "endereco": {"logradouro": "Rua X", "municipio": "Joinville", "uf": "SC"},
    "participantes": {
        "campos_extraidos": [
            {"nome": "TIAGO", "documento": "***", "qualificacao": "socio"},
            {"nome": "SILVIO", "qualificacao": "socio"},
        ],
        "texto": "...",
    },
    "arquivamentos": [
        {"descricao": "11a Alteracao Contratual", "numero": "123456", "sessao": "X"},
    ],
}


def test_map_ficha_campos_principais():
    f = map_ficha(_PAYLOAD)
    assert f.nire == "35.222.333.444"
    assert f.cnpj == "12345678000190"
    assert f.tipo == "LTDA"
    assert f.data_constituicao == date(2006, 1, 30)
    assert f.inicio_atividades == date(2006, 2, 1)
    assert f.capital_valor == Decimal("500000.00")
    assert len(f.participantes) == 2
    assert f.participantes[0]["nome"] == "TIAGO"
    assert len(f.arquivamentos) == 1
    assert f.endereco is not None and f.endereco["uf"] == "SC"


def test_map_ficha_tolerante_a_payload_vazio():
    f = map_ficha({})
    assert f.nire is None
    assert f.cnpj is None
    assert f.participantes == []
    assert f.arquivamentos == []


def test_map_ficha_capital_formatos():
    assert map_ficha({"capital": {"valor": 500000}}).capital_valor == Decimal("500000")
    assert map_ficha({"capital": {"valor": "500000.50"}}).capital_valor == Decimal(
        "500000.50"
    )
    assert map_ficha({"capital": {"valor": "abc"}}).capital_valor is None


def test_fields_to_jsonable_e_json_safe():
    import json

    payload = fields_to_jsonable(map_ficha(_PAYLOAD))
    encoded = json.dumps(payload)  # não pode levantar (Decimal/date convertidos)
    assert "2006-01-30" in encoded
    assert payload["capital_valor"] == 500000.0
