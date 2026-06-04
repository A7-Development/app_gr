"""map_basic_data — extracao de campos cadastrais do envelope BDC.

Payload de referencia = exemplo "Com dados" da doc oficial do dataset
`basic_data` (API de Empresas), reduzido aos campos que o mapper le:
https://docs.bigdatacorp.com.br/plataforma/reference/empresas-dados-cadastrais-basicos
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.integracoes.adapters.data.bigdatacorp.mappers.cadastral import (
    map_basic_data,
)

_PAYLOAD_COM_DADOS = {
    "Result": [
        {
            "MatchKeys": "doc{08378107000107}",
            "BasicData": {
                "TaxIdNumber": "08378107000107",
                "OfficialName": "BIG DATA CORP S.A.",
                "TradeName": "BIGDATACORP",
                "FoundedDate": "2007-04-03T00:00:00Z",
                "Age": 18,
                "TaxIdStatus": "ATIVA",
                "TaxRegime": "LUCRO REAL",
                "Activities": [
                    {"IsMain": True, "Code": "6201501", "Activity": "DESENV SOFTWARE"},
                    {"IsMain": False, "Code": "6202300", "Activity": "LICENCIAMENTO"},
                ],
                "LegalNature": {"Code": "2054", "Activity": "SOCIEDADE ANONIMA FECHADA"},
                "AdditionalOutputData": {
                    "Capital": "OITO MILHOES...",
                    "CapitalRS": "8385000.00",
                },
            },
        }
    ],
    "QueryId": "5db0780a-87b7-4861-a56d-7679fdd0690e",
    "Status": {"basic_data": [{"Code": 0, "Message": "OK"}]},
}

_PAYLOAD_SEM_DADOS = {
    "Result": [],
    "QueryId": "274d1e34-5ff9-41a8-98d6-c484d19987d9",
    "Status": {"basic_data": [{"Code": 0, "Message": "OK"}]},
}


def test_map_com_dados_extrai_silver() -> None:
    res = map_basic_data(_PAYLOAD_COM_DADOS)

    assert res.found is True
    assert res.dataset_status_code == 0
    assert res.query_id == "5db0780a-87b7-4861-a56d-7679fdd0690e"

    f = res.fields
    assert f is not None
    assert f.tax_status == "ATIVA"
    assert f.capital_social == Decimal("8385000.00")
    assert f.founding_date == date(2007, 4, 3)
    assert f.official_name == "BIG DATA CORP S.A."
    assert f.trade_name == "BIGDATACORP"
    assert f.tax_id_number == "08378107000107"
    # cnaes normalizados (code + is_main + name).
    assert f.cnaes == [
        {"code": "6201501", "is_main": True, "name": "DESENV SOFTWARE"},
        {"code": "6202300", "is_main": False, "name": "LICENCIAMENTO"},
    ]
    # raw BasicData preservado pra receita_data.
    assert f.basic_data["TaxRegime"] == "LUCRO REAL"


def test_map_sem_dados_marca_not_found() -> None:
    res = map_basic_data(_PAYLOAD_SEM_DADOS)

    assert res.found is False
    assert res.fields is None
    assert res.dataset_status_code == 0
    assert res.query_id == "274d1e34-5ff9-41a8-98d6-c484d19987d9"


def test_map_status_exterior_preserva_valor_longo() -> None:
    payload = {
        "Result": [
            {
                "BasicData": {
                    "TaxIdStatus": "ATIVA - EMPRESA DOMICILIADA NO EXTERIOR",
                    "Activities": [],
                    "AdditionalOutputData": {},
                }
            }
        ],
        "Status": {"basic_data": [{"Code": 0}]},
    }
    res = map_basic_data(payload)
    assert res.fields is not None
    # 39 chars — exige tax_status String(64) no silver (migration a1c4e7f2b9d3).
    assert res.fields.tax_status == "ATIVA - EMPRESA DOMICILIADA NO EXTERIOR"
    assert res.fields.cnaes == []
    assert res.fields.capital_social is None
    assert res.fields.founding_date is None


def test_map_capital_invalido_e_data_sentinela_viram_none() -> None:
    payload = {
        "Result": [
            {
                "BasicData": {
                    "TaxIdStatus": "ATIVA",
                    "FoundedDate": "0001-01-01T00:00:00Z",
                    "Activities": [{"Code": "4711301", "IsMain": True}],
                    "AdditionalOutputData": {"CapitalRS": ""},
                }
            }
        ],
        "Status": {"basic_data": [{"Code": 0}]},
    }
    res = map_basic_data(payload)
    assert res.fields is not None
    assert res.fields.capital_social is None
    assert res.fields.founding_date is None
    # CNAE sem Activity ainda mapeia (name=None).
    assert res.fields.cnaes == [{"code": "4711301", "is_main": True, "name": None}]
