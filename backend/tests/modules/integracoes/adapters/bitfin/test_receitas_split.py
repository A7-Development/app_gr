"""Split juros x multa da mora de liquidacao (receitas.py).

Invariantes:
- juros + multa == total caixa SEMPRE (o teorico so da a proporcao);
- sem ProcedimentoDeCobranca (percentuais None) -> 100% juros;
- teoricos zerados (pct=0 ou dias<=0 e multa 0) -> 100% juros;
- total <= 0 -> (0, 0).
"""

from decimal import Decimal

from app.modules.integracoes.adapters.erp.bitfin.receitas import (
    split_mora_liquidacao,
)

D = Decimal


def test_split_proporcional_soma_total():
    # Caso real 76459/1: liquido 6361.20, pago 6655.91 (total 294.71),
    # 7 dias de atraso vs venc original.
    juros, multa = split_mora_liquidacao(
        total=D("294.71"),
        valor_liquido=D("6361.20"),
        pct_juros=D("3.0"),
        pct_multa=D("2.0"),
        dias_atraso=7,
    )
    assert juros + multa == D("294.71")
    assert juros > 0 and multa > 0
    # multa_teor (2% flat) > juros_teor (3%/30*7 = 0.7%) -> multa leva mais.
    assert multa > juros


def test_sem_procedimento_de_cobranca_vai_tudo_pra_juros():
    juros, multa = split_mora_liquidacao(
        total=D("100.00"),
        valor_liquido=D("1000.00"),
        pct_juros=None,
        pct_multa=None,
        dias_atraso=10,
    )
    assert (juros, multa) == (D("100.00"), D("0"))


def test_teoricos_zerados_vai_tudo_pra_juros():
    juros, multa = split_mora_liquidacao(
        total=D("50.00"),
        valor_liquido=D("1000.00"),
        pct_juros=D("0"),
        pct_multa=D("0"),
        dias_atraso=5,
    )
    assert (juros, multa) == (D("50.00"), D("0"))


def test_total_nao_positivo_zera():
    assert split_mora_liquidacao(
        total=D("0"),
        valor_liquido=D("1000.00"),
        pct_juros=D("1"),
        pct_multa=D("2"),
        dias_atraso=3,
    ) == (D("0"), D("0"))


def test_dias_negativos_tratados_como_zero():
    # Defensivo: pago "atrasado" vs venc efetiva mas adiantado vs venc
    # original (prorrogado) -> juros_teor 0; multa_teor manda.
    juros, multa = split_mora_liquidacao(
        total=D("80.00"),
        valor_liquido=D("4000.00"),
        pct_juros=D("3.0"),
        pct_multa=D("2.0"),
        dias_atraso=-5,
    )
    assert juros + multa == D("80.00")
    assert juros == D("0")
    assert multa == D("80.00")


def test_arredondamento_centavos_fecha():
    # Proporcao que gera dizima: invariante juros+multa==total segura.
    juros, multa = split_mora_liquidacao(
        total=D("100.01"),
        valor_liquido=D("3333.33"),
        pct_juros=D("1.0"),
        pct_multa=D("1.0"),
        dias_atraso=10,
    )
    assert juros + multa == D("100.01")
    assert juros.as_tuple().exponent == -2
    assert multa.as_tuple().exponent == -2
