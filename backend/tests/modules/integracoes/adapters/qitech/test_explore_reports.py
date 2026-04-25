"""explore_reports — helpers puros (_shape, _parse_tipos)."""

from __future__ import annotations

import pytest

from app.modules.integracoes.adapters.admin.qitech.explore_reports import (
    _parse_tipos,
    _shape,
)


def test_shape_null() -> None:
    assert _shape(None) == "null"


def test_shape_list_empty() -> None:
    assert _shape([]) == "list[0]"


def test_shape_list_with_items() -> None:
    assert _shape([1, 2, 3]) == "list[3]"


def test_shape_dict_small() -> None:
    assert _shape({"a": 1, "b": 2}) == "dict{a, b}"


def test_shape_dict_large_truncates() -> None:
    body = {f"k{i}": i for i in range(10)}
    out = _shape(body)
    # Primeiras 4 chaves + "...+N"
    assert out.startswith("dict{k0, k1, k2, k3")
    assert "...+6" in out


def test_shape_string() -> None:
    assert _shape("hello") == "str(5)"


def test_shape_primitive() -> None:
    assert _shape(42) == "int"
    assert _shape(True) == "bool"


def test_parse_tipos_default_returns_all() -> None:
    pairs = _parse_tipos(None)
    codes = [c for c, _ in pairs]
    # Pelo menos os 23 catalogados hoje.
    assert "outros-fundos" in codes
    assert "rf" in codes
    assert "mec" in codes
    assert len(pairs) >= 23


def test_parse_tipos_subset() -> None:
    pairs = _parse_tipos("outros-fundos,rf")
    assert [c for c, _ in pairs] == ["outros-fundos", "rf"]


def test_parse_tipos_rejects_unknown() -> None:
    with pytest.raises(SystemExit, match="desconhecido"):
        _parse_tipos("outros-fundos,nao-existe")


def test_parse_tipos_empty_string_returns_all() -> None:
    """Argparse pode passar string vazia; tratamos como 'default'."""
    assert len(_parse_tipos("")) >= 23


def test_parse_tipos_whitespace_resilience() -> None:
    pairs = _parse_tipos("  outros-fundos  ,  rf  ")
    assert [c for c, _ in pairs] == ["outros-fundos", "rf"]
