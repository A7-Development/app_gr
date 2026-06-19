"""Unit tests — classify_liquidacao_nature (perda vs giro)."""

import pytest

from app.modules.controladoria.services.liquidacao_natureza import (
    classify_liquidacao_nature,
    is_credit_loss,
    is_known_liquidacao_tipo,
)


@pytest.mark.parametrize(
    "tipo",
    [
        "ABATIMENTO CONCEDIDO",
        "abatimento concedido",
        "Abatimento Concedido",
        "ABATIMENTO PARCIAL CONCEDIDO",
    ],
)
def test_abatimento_e_perda(tipo: str) -> None:
    assert classify_liquidacao_nature(tipo) == "credit_loss"
    assert is_credit_loss(tipo) is True


@pytest.mark.parametrize(
    "tipo",
    [
        "LIQUIDAÇÃO NORMAL",
        "LIQUIDAÇÃO PARCIAL",
        "RECOMPRA PARCIAL SEM ADIANTAMENTO",
        "BAIXA POR DEPOSITO SACADO",
        "BAIXA POR DEPOSITO CEDENTE",
    ],
)
def test_eventos_de_caixa_sao_giro(tipo: str) -> None:
    assert classify_liquidacao_nature(tipo) == "cash_settlement"
    assert is_credit_loss(tipo) is False


@pytest.mark.parametrize("tipo", [None, "", "   ", "TIPO_DESCONHECIDO_NOVO"])
def test_guard_desconhecido_preserva_legado_giro(tipo: str | None) -> None:
    # Desconhecido NUNCA vira perda silenciosa — cai em giro (comportamento legado).
    assert classify_liquidacao_nature(tipo) == "cash_settlement"


@pytest.mark.parametrize(
    "tipo",
    [
        # 8 tipos do rastreamento de todo o historico (abr-jun/2026)
        "ABATIMENTO CONCEDIDO",
        "LIQUIDAÇÃO NORMAL",
        "LIQUIDAÇÃO PARCIAL",
        "LIQUIDAÇÃO EM CARTÓRIO",
        "BAIXA POR DEPOSITO SACADO",
        "BAIXA POR DEPOSITO CEDENTE",
        "BAIXA POR RECOMPRA",
        "RECOMPRA PARCIAL SEM ADIANTAMENTO",
    ],
)
def test_vocabulario_conhecido(tipo: str) -> None:
    assert is_known_liquidacao_tipo(tipo) is True


@pytest.mark.parametrize("tipo", [None, "", "PERDA NEGOCIADA", "TIPO_NOVO_QITECH"])
def test_tipo_novo_e_desconhecido_failloud(tipo: str | None) -> None:
    # Tipo fora do vocabulario rastreado -> detectavel (fail-loud), nao silencioso.
    assert is_known_liquidacao_tipo(tipo) is False
