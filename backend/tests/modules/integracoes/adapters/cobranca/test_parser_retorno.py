"""Parser CNAB400 de retorno: posicoes dos campos, incluindo praca de liquidacao.

Linha sintetica montada campo a campo nas posicoes 1-based do layout Bradesco
(mesmo layout de BMP/Vortx). Os valores espelham um caso real validado em
2026-07-07 (liquidacao JCL 5101/3: Sicoob 756 ag 07723, credito D+1).
"""

from __future__ import annotations

from app.modules.integracoes.adapters.cobranca.bradesco.parser import parse_retorno
from app.modules.integracoes.adapters.cobranca.decode_evento import _praca_field

_WIDTH = 400


def _make_line(tipo: str, fields: dict[tuple[int, int], str]) -> str:
    """Monta uma linha CNAB de 400 chars com campos em posicoes 1-based."""
    buf = [" "] * _WIDTH
    buf[0] = tipo
    for (start, end), value in fields.items():
        assert len(value) <= end - start + 1, f"valor nao cabe em {start}-{end}"
        for i, ch in enumerate(value):
            buf[start - 1 + i] = ch
    return "".join(buf)


def _arquivo_retorno() -> str:
    header = _make_line("0", {(95, 100): "160626"})
    detalhe = _make_line(
        "1",
        {
            (38, 62): "DID102904",
            (71, 82): "600000021344",
            (109, 110): "06",
            (111, 116): "150626",
            (117, 126): "5101/3",
            (147, 152): "150626",
            (153, 165): "0000000661563",
            (166, 168): "756",
            (169, 173): "07723",
            (254, 266): "0000000661563",
            (296, 301): "160626",
        },
    )
    trailer = _make_line("9", {})
    return "\n".join([header, detalhe, trailer])


def test_parse_retorno_extrai_praca_de_liquidacao() -> None:
    parsed = parse_retorno(_arquivo_retorno())

    assert parsed.data_ref_raw == "160626"
    assert len(parsed.ocorrencias) == 1
    p = parsed.ocorrencias[0].payload
    assert p["codigo_ocorrencia"] == "06"
    assert p["nosso_numero"] == "600000021344"
    assert p["numero_documento"] == "5101/3"
    assert p["valor_pago"] == "0000000661563"
    # Campos novos (v1.3.0): praca de liquidacao.
    assert p["banco_pagador"] == "756"
    assert p["agencia_pagadora"] == "07723"
    assert p["data_credito"] == "160626"


def test_parse_retorno_praca_vazia_em_evento_sem_liquidacao() -> None:
    detalhe = _make_line(
        "1",
        {
            (71, 82): "600000021344",
            (109, 110): "02",  # entrada confirmada: sem praca
            (111, 116): "040526",
            (117, 126): "5101/3",
            (166, 168): "000",
            (169, 173): "00000",
        },
    )
    parsed = parse_retorno("\n".join([_make_line("0", {(95, 100): "040526"}), detalhe]))
    p = parsed.ocorrencias[0].payload
    # Parser e bronze-fiel: guarda o cru; a normalizacao e do decode.
    assert p["banco_pagador"] == "000"
    assert p["agencia_pagadora"] == "00000"
    assert p["data_credito"] == ""


def test_praca_field_normaliza_zeros_e_preserva_zeros_a_esquerda() -> None:
    assert _praca_field("756") == "756"
    assert _praca_field("07723") == "07723"  # zero a esquerda preservado
    assert _praca_field("000") is None
    assert _praca_field("00000") is None
    assert _praca_field("") is None
    assert _praca_field(None) is None
    assert _praca_field("  ") is None
