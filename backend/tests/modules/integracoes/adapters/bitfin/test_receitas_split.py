"""Split da mora de liquidacao pela REGUA (receitas.py) — 3 saidas.

Decisao 2026-06-11: decompoe juros x multa APENAS quando o caixa seguiu a
regua contratual (|total - regua| <= TOLERANCIA_REGUA); fora disso o
pagamento e acordo -> 'negociado', sem decomposicao (decompor seria
inferencia). Invariantes:
- caso 'regua': juros + multa == total, ambos >= 0;
- caso 'negociado': juros = multa = 0; regua teorica retornada p/ referencia;
- total <= 0 -> (0, 0).
"""

from decimal import Decimal

from app.modules.integracoes.adapters.erp.bitfin.receitas import (
    TOLERANCIA_REGUA,
    regua_contratual,
    split_mora_liquidacao,
)

D = Decimal


def test_pagamento_na_regua_decompoe_exato():
    # liquido 1000, 2% multa + 3% a.m. por 10 dias: regua = 20.00 + 10.00.
    resultado, juros, multa, teorico = split_mora_liquidacao(
        total=D("30.00"),
        valor_liquido=D("1000.00"),
        pct_juros=D("3.0"),
        pct_multa=D("2.0"),
        dias_atraso=10,
    )
    assert resultado == "regua"
    assert (juros, multa) == (D("10.00"), D("20.00"))
    assert teorico == D("30.00")


def test_arredondamento_bancario_residuo_no_juros():
    # Pago 30.40 vs regua 30.00 (CNAB arredonda pro-rata): ainda regua;
    # residuo de 0.40 vai pro juros; invariante juros+multa==total.
    resultado, juros, multa, _ = split_mora_liquidacao(
        total=D("30.40"),
        valor_liquido=D("1000.00"),
        pct_juros=D("3.0"),
        pct_multa=D("2.0"),
        dias_atraso=10,
    )
    assert resultado == "regua"
    assert juros + multa == D("30.40")
    assert multa == D("20.00")


def test_fora_da_tolerancia_vira_negociado_sem_split():
    # Pago 19323.02 vs regua ~27156 (caso Quimassa): acordo.
    resultado, juros, multa, teorico = split_mora_liquidacao(
        total=D("19323.02"),
        valor_liquido=D("783365.56"),
        pct_juros=D("7.0"),
        pct_multa=D("3.0"),
        dias_atraso=2,
    )
    assert resultado == "negociado"
    assert (juros, multa) == (D("0"), D("0"))
    assert teorico > D("19323.02")  # referencia p/ desconto concedido


def test_sem_procedimento_de_cobranca_vira_negociado():
    # Sem regua nao ha como afirmar decomposicao: negociado (teorico 0).
    resultado, _juros, _multa, teorico = split_mora_liquidacao(
        total=D("100.00"),
        valor_liquido=D("1000.00"),
        pct_juros=None,
        pct_multa=None,
        dias_atraso=10,
    )
    assert resultado == "negociado"
    assert teorico == D("0.00")


def test_total_nao_positivo_zera():
    resultado, juros, multa, _ = split_mora_liquidacao(
        total=D("0"),
        valor_liquido=D("1000.00"),
        pct_juros=D("1"),
        pct_multa=D("2"),
        dias_atraso=3,
    )
    assert resultado == "regua"
    assert (juros, multa) == (D("0"), D("0"))


def test_tolerancia_limite():
    # Exatamente na borda da tolerancia: ainda regua.
    resultado, juros, multa, _ = split_mora_liquidacao(
        total=D("30.00") + TOLERANCIA_REGUA,
        valor_liquido=D("1000.00"),
        pct_juros=D("3.0"),
        pct_multa=D("2.0"),
        dias_atraso=10,
    )
    assert resultado == "regua"
    assert juros + multa == D("30.00") + TOLERANCIA_REGUA


def test_regua_contratual_componentes():
    juros, multa = regua_contratual(
        base=D("6361.20"), pct_juros=D("3.0"), pct_multa=D("2.0"), dias_atraso=7,
    )
    # juros = 6361.20 * 3%/30 * 7 = 44.53; multa = 127.22
    assert juros == D("44.53")
    assert multa == D("127.22")
    # dias negativos = 0 (pago antes do venc original em titulo prorrogado)
    juros, _ = regua_contratual(
        base=D("1000"), pct_juros=D("3.0"), pct_multa=D("0"), dias_atraso=-5,
    )
    assert juros == D("0.00")
