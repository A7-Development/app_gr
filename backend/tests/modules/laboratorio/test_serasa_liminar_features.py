"""Extractor de features da tese de liminar — nucleos puros."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.modules.laboratorio.services.serasa_liminar_features import (
    compute_longitudinal,
    idade_empresa_anos,
)

_ZEROS = {
    "count_pefin": 0,
    "count_refin": 0,
    "count_protesto": 0,
    "count_cheque": 0,
    "count_falencias": 0,
    "count_acoes_judiciais": 0,
}


def test_primeira_consulta_sem_longitudinal() -> None:
    out = compute_longitudinal(_ZEROS, None)
    assert out == {
        "delta_negativos": None,
        "categorias_zeradas": None,
        "zerou_em_bloco": False,
    }


def test_zerou_em_bloco_assinatura_de_liminar() -> None:
    # 26 protestos + 2 acoes + 3 pefin -> tudo zero numa consulta.
    anterior = {
        **_ZEROS,
        "count_protesto": 26,
        "count_acoes_judiciais": 2,
        "count_pefin": 3,
    }
    out = compute_longitudinal(_ZEROS, anterior)
    assert out["delta_negativos"] == -31
    assert out["categorias_zeradas"] == 3
    assert out["zerou_em_bloco"] is True


def test_pagamento_gradual_nao_e_bloco() -> None:
    # So 1 categoria zerou (pagou os pefins); protestos continuam.
    anterior = {**_ZEROS, "count_pefin": 2, "count_protesto": 5}
    atual = {**_ZEROS, "count_protesto": 5}
    out = compute_longitudinal(atual, anterior)
    assert out["categorias_zeradas"] == 1
    assert out["zerou_em_bloco"] is False


def test_piora_tem_delta_positivo() -> None:
    anterior = {**_ZEROS, "count_protesto": 1}
    atual = {**_ZEROS, "count_protesto": 4}
    out = compute_longitudinal(atual, anterior)
    assert out["delta_negativos"] == 3
    assert out["categorias_zeradas"] == 0
    assert out["zerou_em_bloco"] is False


def test_idade_empresa() -> None:
    consulted = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    assert idade_empresa_anos(date(2016, 6, 10), consulted) == 10.0
    assert idade_empresa_anos(None, consulted) is None
