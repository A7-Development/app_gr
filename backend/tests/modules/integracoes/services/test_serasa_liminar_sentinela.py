"""Sentinela de liminar — nucleo puro da maquina de estados.

Transicoes desenhadas 2026-06-10 (Ricardo): CNPJ que recebeu "NADA
CONSTA" nunca sai silenciosamente da deteccao — so transiciona com
evento auditavel.
"""

from __future__ import annotations

from app.modules.integracoes.services.serasa_liminar_sentinela import (
    ESTADO_LIMINAR_CAIDA,
    ESTADO_SUSPEITA_ATIVA,
    ESTADO_TRANSICAO_AMBIGUA,
    TRANSICAO_AMBIGUA,
    TRANSICAO_ENTRADA,
    TRANSICAO_LIMINAR_CAIDA,
    TRANSICAO_REATIVADA,
    decidir_transicao,
    has_negativos_visiveis,
)

# ─── Entrada na maquina ────────────────────────────────────────────────────


def test_sem_estado_nada_consta_entra_suspeita() -> None:
    assert decidir_transicao(
        None, nada_consta=True, negativos_visiveis=False
    ) == (ESTADO_SUSPEITA_ATIVA, TRANSICAO_ENTRADA)


def test_sem_estado_consulta_normal_fora_da_maquina() -> None:
    assert decidir_transicao(
        None, nada_consta=False, negativos_visiveis=True
    ) == (None, None)
    assert decidir_transicao(
        None, nada_consta=False, negativos_visiveis=False
    ) == (None, None)


# ─── Suspeita ativa ────────────────────────────────────────────────────────


def test_suspeita_confirmada_sem_evento() -> None:
    assert decidir_transicao(
        ESTADO_SUSPEITA_ATIVA, nada_consta=True, negativos_visiveis=False
    ) == (None, None)


def test_negativos_reaparecem_liminar_caida() -> None:
    assert decidir_transicao(
        ESTADO_SUSPEITA_ATIVA, nada_consta=False, negativos_visiveis=True
    ) == (ESTADO_LIMINAR_CAIDA, TRANSICAO_LIMINAR_CAIDA)


def test_limpo_sem_carimbo_transicao_ambigua() -> None:
    # Cenario do ponto cego: Serasa troca o marcador, negativos seguem
    # zerados — vira ambiguo (sentinela sistemica decide pelo agregado).
    assert decidir_transicao(
        ESTADO_SUSPEITA_ATIVA, nada_consta=False, negativos_visiveis=False
    ) == (ESTADO_TRANSICAO_AMBIGUA, TRANSICAO_AMBIGUA)


# ─── Estados pos-transicao ─────────────────────────────────────────────────


def test_nada_consta_reativa_de_caida_e_ambigua() -> None:
    for anterior in (ESTADO_LIMINAR_CAIDA, ESTADO_TRANSICAO_AMBIGUA):
        assert decidir_transicao(
            anterior, nada_consta=True, negativos_visiveis=False
        ) == (ESTADO_SUSPEITA_ATIVA, TRANSICAO_REATIVADA)


def test_caida_e_ambigua_sao_terminais_sem_novo_carimbo() -> None:
    for anterior in (ESTADO_LIMINAR_CAIDA, ESTADO_TRANSICAO_AMBIGUA):
        for negativos in (True, False):
            assert decidir_transicao(
                anterior, nada_consta=False, negativos_visiveis=negativos
            ) == (None, None)


# ─── Negativos visiveis ────────────────────────────────────────────────────


def test_has_negativos_considera_todas_categorias() -> None:
    base = {
        "count_pefin": 0,
        "count_refin": 0,
        "count_protesto": 0,
        "count_cheque": 0,
        "count_falencias": 0,
        "count_acoes_judiciais": 0,
    }
    assert has_negativos_visiveis(base) is False
    for campo in base:
        assert has_negativos_visiveis({**base, campo: 1}) is True


def test_has_negativos_tolera_campos_ausentes_e_none() -> None:
    assert has_negativos_visiveis({}) is False
    assert has_negativos_visiveis({"count_pefin": None}) is False
