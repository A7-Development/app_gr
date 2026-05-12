"""Avaliacao de predicates JSON para regras COSIF.

Formato suportado (recursivo):

    {"field": "<col>", "op": "<op>", "value": <v>}      # leaf
    {"all": [...predicates]}                            # AND
    {"any": [...predicates]}                            # OR

Operadores leaf:
    eq             igualdade exata
    ne             diferente
    in             value e lista
    contains       substring (case-sensitive)
    contains_ci    substring (case-insensitive)
    starts_with    prefixo (case-sensitive)
    ends_with      sufixo
    qtde_signal    "positive" / "negative" / "zero" — usa Decimal

Acessor de field: faz `row.get(field)`. Comparacao tolerante a None
(retorna False para qualquer leaf com value/row None, exceto eq None).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def match(predicate: dict[str, Any], row: dict[str, Any]) -> bool:
    """Avalia um predicate JSON contra um row de silver.

    Retorna True quando o predicate combina. Predicate vazio ({"all": []}
    ou {}) sempre combina — util para regras fallback.
    """
    if "all" in predicate:
        sub = predicate["all"]
        return all(match(s, row) for s in sub) if sub else True
    if "any" in predicate:
        sub = predicate["any"]
        return any(match(s, row) for s in sub) if sub else False
    if "field" in predicate:
        return _match_leaf(predicate, row)
    # Predicate vazio = sempre verdadeiro (fallback).
    return True


def _match_leaf(predicate: dict[str, Any], row: dict[str, Any]) -> bool:
    field = predicate["field"]
    op = predicate["op"]
    value = predicate.get("value")
    raw = row.get(field)

    if op == "eq":
        return raw == value
    if op == "ne":
        return raw != value
    if op == "in":
        return raw in (value or [])

    if raw is None:
        # Operadores de texto/quantidade abaixo nao matcham None.
        return False

    if op == "contains":
        return str(value) in str(raw)
    if op == "contains_ci":
        return str(value).upper() in str(raw).upper()
    if op == "starts_with":
        return str(raw).startswith(str(value))
    if op == "ends_with":
        return str(raw).endswith(str(value))
    if op == "qtde_signal":
        try:
            q = Decimal(str(raw))
        except (ValueError, ArithmeticError):
            return False
        if value == "positive":
            return q > 0
        if value == "negative":
            return q < 0
        if value == "zero":
            return q == 0
        return False

    return False
