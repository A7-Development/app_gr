"""Tests do avaliador de predicates JSON para regras COSIF.

Funções puras — sem DB, sem fixtures.
"""

from app.modules.controladoria.services.cosif.predicates import match


# ─── Leaf operators ──────────────────────────────────────────────────────────

def test_eq_matches() -> None:
    assert match({"field": "k", "op": "eq", "value": "X"}, {"k": "X"}) is True


def test_eq_does_not_match() -> None:
    assert match({"field": "k", "op": "eq", "value": "X"}, {"k": "Y"}) is False


def test_ne_matches() -> None:
    assert match({"field": "k", "op": "ne", "value": "X"}, {"k": "Y"}) is True


def test_in_matches() -> None:
    assert match({"field": "k", "op": "in", "value": ["A", "B"]}, {"k": "B"}) is True


def test_in_does_not_match() -> None:
    assert match({"field": "k", "op": "in", "value": ["A", "B"]}, {"k": "C"}) is False


def test_contains_case_sensitive() -> None:
    assert match({"field": "k", "op": "contains", "value": "foo"}, {"k": "foobar"}) is True
    assert match({"field": "k", "op": "contains", "value": "FOO"}, {"k": "foobar"}) is False


def test_contains_ci_case_insensitive() -> None:
    assert match({"field": "k", "op": "contains_ci", "value": "FOO"}, {"k": "foobar"}) is True
    assert match({"field": "k", "op": "contains_ci", "value": "foo"}, {"k": "FOOBAR"}) is True


def test_starts_with() -> None:
    assert match({"field": "k", "op": "starts_with", "value": "SR"}, {"k": "SRP"}) is True
    assert match({"field": "k", "op": "starts_with", "value": "SR"}, {"k": "MEZ"}) is False


def test_ends_with() -> None:
    assert match({"field": "k", "op": "ends_with", "value": "PX"}, {"k": "NCPX"}) is True


def test_qtde_signal_positive() -> None:
    pos = {"field": "q", "op": "qtde_signal", "value": "positive"}
    assert match(pos, {"q": "100"}) is True
    assert match(pos, {"q": "-100"}) is False
    assert match(pos, {"q": "0"}) is False


def test_qtde_signal_negative() -> None:
    neg = {"field": "q", "op": "qtde_signal", "value": "negative"}
    assert match(neg, {"q": "-100"}) is True
    assert match(neg, {"q": "100"}) is False


def test_qtde_signal_zero() -> None:
    zero = {"field": "q", "op": "qtde_signal", "value": "zero"}
    assert match(zero, {"q": "0"}) is True
    assert match(zero, {"q": "0.00"}) is True
    assert match(zero, {"q": "0.001"}) is False


def test_leaf_none_value_in_row() -> None:
    # Operadores de texto/qtde nao matcham None — devem retornar False.
    assert match({"field": "k", "op": "contains", "value": "X"}, {"k": None}) is False
    assert match({"field": "k", "op": "qtde_signal", "value": "negative"}, {"k": None}) is False
    # eq com None faz comparacao direta.
    assert match({"field": "k", "op": "eq", "value": None}, {"k": None}) is True


# ─── Combinators ─────────────────────────────────────────────────────────────

def test_all_empty_matches() -> None:
    """{"all":[]} sempre verdadeiro — usado como fallback genérico."""
    assert match({"all": []}, {}) is True


def test_any_empty_does_not_match() -> None:
    """{"any":[]} sempre falso — vacuous OR."""
    assert match({"any": []}, {}) is False


def test_all_combines_with_and() -> None:
    row = {"q": "-100", "p": "SRP"}
    pred = {"all": [
        {"field": "q", "op": "qtde_signal", "value": "negative"},
        {"field": "p", "op": "starts_with", "value": "SR"},
    ]}
    assert match(pred, row) is True
    # Quebra uma das condicoes.
    assert match(pred, {**row, "p": "MEZ"}) is False
    assert match(pred, {**row, "q": "100"}) is False


def test_any_combines_with_or() -> None:
    pred = {"any": [
        {"field": "p", "op": "starts_with", "value": "SR"},
        {"field": "p", "op": "starts_with", "value": "MEZ"},
    ]}
    assert match(pred, {"p": "SRP"}) is True
    assert match(pred, {"p": "MEZAN"}) is True
    assert match(pred, {"p": "NCPX"}) is False


def test_nested_all_any() -> None:
    # Regra real do seed: cota emitida (qtde<0 AND papel in (SR|MEZ|SUB)).
    pred = {"all": [
        {"field": "q", "op": "qtde_signal", "value": "negative"},
        {"any": [
            {"field": "p", "op": "starts_with", "value": "SR"},
            {"field": "p", "op": "starts_with", "value": "MEZ"},
            {"field": "p", "op": "starts_with", "value": "SUB"},
        ]},
    ]}
    assert match(pred, {"q": "-100", "p": "SRP"}) is True
    assert match(pred, {"q": "-50", "p": "MEZAN"}) is True
    assert match(pred, {"q": "100", "p": "SRP"}) is False  # qtde positiva
    assert match(pred, {"q": "-100", "p": "NTN-B"}) is False  # papel errado
