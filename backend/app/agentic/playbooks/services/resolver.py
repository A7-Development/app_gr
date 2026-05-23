"""Template resolver — `{{node.X.output.field}}` and friends.

This is the core of the "fluxo de dados" filosofia (n8n-style):
nodes reference outputs of preceding nodes via dotted-path templates in
their config. The engine resolves templates against the runtime context
RIGHT BEFORE executing each node — so config like:

    {"entity_ref": "{{node.pleito.output.target_cnpj}}"}

becomes, at execution time:

    {"entity_ref": "12.345.678/0001-90"}

Context shape (engine builds this per-run):
    {
        "trigger": {...},   # = run.trigger_data
        "node": {           # = run.context_data
            "<node_id>": {"output": {...}, "status_hint": "..."},
            ...
        },
    }

Path semantics:
- Dotted: `node.pleito.output.target_cnpj`
- List index: `node.bureaus.output.results.0.score`
- Missing path → None (renders as empty string in interpolation;
  raw None when the template covers the whole value)

Edge conditions also use this resolver. Examples:
    "{{node.branch.output.result}} == true"
    "{{node.score.output.value}} >= 700"
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Matches {{ path.to.value }} - non-greedy until }}
_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def resolve_templates(value: Any, context: dict[str, Any]) -> Any:
    """Recursively resolve `{{...}}` templates in a value tree.

    Handles strings, dicts, lists. Other types pass through unchanged.

    Special case: when a string contains EXACTLY one template AND nothing
    else (after stripping), the raw resolved value is returned (preserving
    type — number, dict, list, etc). When mixed with literal text, the
    result is a string with each `{{...}}` substituted.

    >>> resolve_templates("{{x}}", {"x": 42})
    42
    >>> resolve_templates("hello {{name}}", {"name": "world"})
    'hello world'
    >>> resolve_templates({"a": "{{x}}", "b": [1, "{{y}}"]}, {"x": 1, "y": 2})
    {'a': 1, 'b': [1, 2]}
    """
    if isinstance(value, str):
        return _resolve_string(value, context)
    if isinstance(value, dict):
        return {k: resolve_templates(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_templates(v, context) for v in value]
    return value


def _resolve_string(s: str, context: dict[str, Any]) -> Any:
    matches = list(_TEMPLATE_RE.finditer(s))
    if not matches:
        return s

    # If the entire string is a single template, return the raw value
    # (so `{{x}}` where x=42 returns int 42, not "42").
    if len(matches) == 1:
        full_match = matches[0]
        if full_match.group(0) == s.strip():
            return _walk_path(full_match.group(1), context)

    # Otherwise, do string interpolation: substitute each match.
    def replacer(m: re.Match[str]) -> str:
        v = _walk_path(m.group(1), context)
        if v is None:
            return ""
        return str(v)

    return _TEMPLATE_RE.sub(replacer, s)


def _walk_path(path: str, context: dict[str, Any]) -> Any:
    """Walk a dotted path through nested dicts/lists. Returns None if not found."""
    parts = [p.strip() for p in path.split(".") if p.strip()]
    cur: Any = context
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list):
            try:
                cur = cur[int(p)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if cur is None:
            return None
    return cur


# ─── Edge condition evaluation ─────────────────────────────────────────────


def evaluate_edge_condition(
    condition: str,
    context: dict[str, Any],
) -> bool:
    """Evaluate an edge condition string. Returns True if the edge is active.

    The condition is a string that may include `{{...}}` templates. After
    resolving templates, the result is parsed as a simple boolean expression:

    Supported forms:
    - "true" / "false"           — literal
    - "<value>"                  — truthiness of a single resolved value
    - "<a> == <b>"              — equality (string compare after resolve)
    - "<a> != <b>"              — inequality
    - "<a> >= <b>"              — numeric (parses both sides as float)
    - "<a> > <b>"
    - "<a> <= <b>"
    - "<a> < <b>"

    Anything else returns True (open-default — non-conditional edges always
    pass). Errors are logged and treated as "edge passes" (graceful).

    This is intentionally a tiny grammar — NOT a Python eval. Sandboxed.
    """
    if not condition or not condition.strip():
        return True

    try:
        resolved = _resolve_string(condition, context)
        if not isinstance(resolved, str):
            # Single template returned a raw value — interpret as boolean.
            return _to_bool(resolved)

        s = resolved.strip()
        if not s:
            return True

        # Literal booleans.
        lower = s.lower()
        if lower in {"true", "1", "yes"}:
            return True
        if lower in {"false", "0", "no", "none", "null"}:
            return False

        # Comparison operators (longest match first).
        for op in ("==", "!=", ">=", "<=", ">", "<"):
            if op in s:
                left, right = s.split(op, 1)
                left_v = left.strip().strip("'\"")
                right_v = right.strip().strip("'\"")
                return _compare(left_v, right_v, op)

        # Single value — truthiness.
        return _to_bool(s.strip("'\""))
    except Exception as e:
        logger.warning(
            "evaluate_edge_condition: error evaluating %r: %s. Defaulting to True.",
            condition,
            e,
        )
        return True


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        lower = v.strip().lower()
        if lower in {"", "false", "0", "no", "none", "null"}:
            return False
        return True
    return bool(v)


def _compare(left: str, right: str, op: str) -> bool:
    # Try numeric comparison first.
    try:
        ln = float(left)
        rn = float(right)
        if op == "==":
            return ln == rn
        if op == "!=":
            return ln != rn
        if op == ">=":
            return ln >= rn
        if op == "<=":
            return ln <= rn
        if op == ">":
            return ln > rn
        if op == "<":
            return ln < rn
    except (ValueError, TypeError):
        pass

    # Fall back to string compare.
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    # Lexicographic compare for >, <, >=, <= on strings.
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    return True
