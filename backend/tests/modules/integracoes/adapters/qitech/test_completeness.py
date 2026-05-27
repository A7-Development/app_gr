"""Completeness assessor — catalogo de classes + sanidade de valor (unit).

Cobre o bug de 2026-05-25: a QiTech publicou a Subordinada zerada
(patrimonio=0, variaçãoDiaria=-100) e o assessor antigo (presenca por nome)
marcou `complete`, congelando lixo. Com o catalogo de `clienteId`, classe
zerada vira `partial`. Sem catalogo, o comportamento legado e preservado.
"""

from __future__ import annotations

from app.modules.integracoes.adapters.admin.qitech.completeness import (
    assess_completeness,
)

_UA_NOME = "REALINVEST FIDC"
_EXPECTED = {"REALINVEST", "REALINVEST MEZ", "REALINVEST SEN"}


def _item(
    cliente_id: str,
    cliente_nome: str,
    patrimonio: float,
    var_diaria: float,
) -> dict:
    return {
        "clienteId": cliente_id,
        "clienteNome": cliente_nome,
        "patrimonio": patrimonio,
        "variaçãoDiaria": var_diaria,
    }


def _mec_payload(*items: dict) -> dict:
    return {"relatórios": {"mec": list(items)}}


# Tres classes saudaveis (caso normal).
_SUB_OK = _item("REALINVEST", "REALINVEST FIDC", 12_057_383.25, 0.31)
_MEZ_OK = _item("REALINVEST MEZ", "REALINVEST FIDC MEZANINO 1", 2_680_879.60, 0.07)
_SEN_OK = _item("REALINVEST SEN", "REALINVEST FIDC SENIOR 1", 12_546_340.71, 0.07)
# Subordinada publicada zerada (assinatura do lixo transitorio).
_SUB_ZEROED = _item("REALINVEST", "REALINVEST FIDC", 0.0, -100.0)


def _assess(payload, *, expected=_EXPECTED, tipo="mec", http=200, ua=_UA_NOME):
    return assess_completeness(
        tipo_de_mercado=tipo,
        payload=payload,
        http_status=http,
        ua_nome=ua,
        expected_classes=expected,
    )


def test_all_classes_sane_is_complete():
    assert _assess(_mec_payload(_SUB_OK, _MEZ_OK, _SEN_OK)) == "complete"


def test_zeroed_sub_is_partial():
    # Sub presente no payload, mas zerada com queda >50% -> nao-publicada-de-verdade.
    assert _assess(_mec_payload(_SUB_ZEROED, _MEZ_OK, _SEN_OK)) == "partial"


def test_missing_class_is_partial():
    # So 2 das 3 classes esperadas (Sub ausente).
    assert _assess(_mec_payload(_MEZ_OK, _SEN_OK)) == "partial"


def test_no_items_is_empty():
    assert _assess(_mec_payload()) == "empty"


def test_http_non_200_is_empty():
    assert _assess(_mec_payload(_SUB_OK, _MEZ_OK, _SEN_OK), http=404) == "empty"


def test_value_sane_boundary_minus_49_is_complete():
    sub = _item("REALINVEST", "REALINVEST FIDC", 0.0, -49.0)
    # -49 nao cruza o limiar de -50 -> ainda considerado sao.
    assert _assess(_mec_payload(sub, _MEZ_OK, _SEN_OK)) == "complete"


def test_value_sane_boundary_minus_50_is_partial():
    sub = _item("REALINVEST", "REALINVEST FIDC", 0.0, -50.0)
    assert _assess(_mec_payload(sub, _MEZ_OK, _SEN_OK)) == "partial"


def test_positive_patrimonio_with_big_drop_is_sane():
    # patrimonio>0 nunca e lixo, mesmo com variacao muito negativa.
    sub = _item("REALINVEST", "REALINVEST FIDC", 1_000.0, -90.0)
    assert _assess(_mec_payload(sub, _MEZ_OK, _SEN_OK)) == "complete"


def test_sub_only_endpoint_not_falsely_partial():
    # conta-corrente so carrega a Subordinada: 1 classe esperada, presente+sa.
    payload = {"relatórios": {"conta-corrente": [_SUB_OK]}}
    assert (
        _assess(payload, expected={"REALINVEST"}, tipo="conta-corrente")
        == "complete"
    )


def test_unparseable_values_are_not_punished():
    sub = _item("REALINVEST", "REALINVEST FIDC", "n/a", None)
    assert _assess(_mec_payload(sub, _MEZ_OK, _SEN_OK)) == "complete"


# ─── Fallback gracioso: sem catalogo -> heuristica legada (sem regressao) ────


def test_no_catalog_none_falls_back_to_legacy_complete():
    # expected_classes=None: caminho legado (_assess_mec por nome). A Sub
    # zerada AINDA tem clienteNome "REALINVEST FIDC" -> presenca por nome ok
    # -> complete (exatamente o comportamento de hoje, preservado).
    assert _assess(_mec_payload(_SUB_ZEROED, _MEZ_OK, _SEN_OK), expected=None) == "complete"


def test_no_catalog_empty_set_falls_back_to_legacy():
    assert _assess(_mec_payload(_SUB_ZEROED, _MEZ_OK, _SEN_OK), expected=set()) == "complete"


def test_legacy_missing_class_still_partial():
    # Sem catalogo, faltando a Mezanino por nome -> legado retorna partial.
    assert _assess(_mec_payload(_SUB_OK, _SEN_OK), expected=None) == "partial"
