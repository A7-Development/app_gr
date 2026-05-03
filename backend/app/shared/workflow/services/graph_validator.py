"""Graph validator — semantic validation of a workflow definition.

Where structural validation lives:
- Pydantic schema (`WorkflowGraph`) — required fields on `NodeSpec`/`EdgeSpec`.
- `engine._topological_levels` — cycle detection + edge integrity.
- `BaseNode.validate_config()` — per-node required config keys.

This module adds the missing layer: **data-flow validation**. For each
node, we ask `node.requires()` and confirm that:
- The dotted path in `Requirement.expr` resolves to some upstream node's
  `produces()` entry — i.e. someone before this node actually publishes
  that variable.
- The semantic type matches (e.g. `Serasa` requires `cnpj: VarType.CNPJ`,
  the upstream `human_input` field has `type=cnpj` → `VarType.CNPJ` →
  ✅; if upstream produced `VarType.STRING`, that's a type mismatch
  warning).

Returns a list of `ValidationError`. Empty = graph is sound.

Shape of `expr` understood:
- `trigger.<key>`  → resolves against the `trigger` node's `produces()`.
- `node.<id>.output.<key>` → resolves against `<id>`'s `produces()`.

Other paths fall through silently (the resolver tolerates missing paths,
so we don't fail validation on patterns we don't yet model).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.shared.workflow.nodes._base import Requirement, VarType
from app.shared.workflow.nodes.registry import get_node_class
from app.shared.workflow.schemas.definition import NodeSpec, WorkflowGraph

__all__ = [
    "ValidationError",
    "ValidationResult",
    "validate_graph",
]


@dataclass(slots=True)
class ValidationError:
    """One semantic issue found in the workflow graph.

    Severity:
    - "error": blocks save / publish (e.g. Serasa needs CNPJ that nobody upstream provides)
    - "warning": surface but allow save (e.g. node references trigger.field that may be runtime-only)
    """

    node_id: str
    severity: str               # "error" | "warning"
    code: str                   # machine-readable, e.g. "missing_upstream"
    message: str                # pt-BR, user-facing
    requirement: str | None = None    # name of the requirement that failed
    expected_type: str | None = None  # e.g. "cnpj"
    found_type: str | None = None     # the type the upstream actually publishes


@dataclass(slots=True)
class ValidationResult:
    has_errors: bool
    errors: list[ValidationError] = field(default_factory=list)
    # `produced_by_node[node_id] = { var_name: vartype_str }` — exposed pra
    # UI renderizar chips de output tipados em cada nó (Fase 3a). É
    # config-aware: se um `human_input` adiciona/remove fields, o que ele
    # publica muda. Captura os produces resolvidos no walk topológico.
    produced_by_node: dict[str, dict[str, str]] = field(default_factory=dict)


_TRIGGER_PATH_RE = re.compile(r"^\s*trigger\.([A-Za-z_][A-Za-z0-9_]*)\s*$")
_NODE_PATH_RE = re.compile(
    r"^\s*node\.([A-Za-z0-9_-]+)\.output\.([A-Za-z_][A-Za-z0-9_]*)\s*$"
)


def _topological_order(graph: WorkflowGraph) -> list[NodeSpec]:
    """Kahn's algorithm — same logic as engine._topological_levels but
    flattened to a single list. Returns nodes in execution order.
    """
    in_degree: dict[str, int] = defaultdict(int)
    children: dict[str, list[str]] = defaultdict(list)
    by_id: dict[str, NodeSpec] = {n.id: n for n in graph.nodes}
    for n in graph.nodes:
        in_degree[n.id] = 0
    for e in graph.edges:
        if e.source in by_id and e.target in by_id:
            in_degree[e.target] += 1
            children[e.source].append(e.target)
    queue = sorted([nid for nid, d in in_degree.items() if d == 0])
    out: list[NodeSpec] = []
    while queue:
        nid = queue.pop(0)
        out.append(by_id[nid])
        for c in sorted(children[nid]):
            in_degree[c] -= 1
            if in_degree[c] == 0:
                queue.append(c)
        queue.sort()
    # Append any nodes left out of topological order (shouldn't happen
    # without a cycle; defensive).
    for n in graph.nodes:
        if n not in out:
            out.append(n)
    return out


def _instantiate(node: NodeSpec) -> Any | None:
    """Try to instantiate the node. Returns None if its `validate_config`
    raises — the structural validator will report that separately.
    """
    try:
        cls = get_node_class(node.type)
    except KeyError:
        return None
    try:
        return cls(node.config or {})
    except (ValueError, TypeError, KeyError):
        return None


def _types_compatible(expected: VarType, found: VarType) -> bool:
    """Are two VarTypes compatible for the purposes of validation?

    MVP rules:
    - Identical types match.
    - STRING is a "wildcard sink": accepts anything (downstream is free
      to interpret).
    - OBJECT is also wildcard (escape hatch).
    - LIST same.
    """
    if expected == found:
        return True
    # STRING/OBJECT/LIST act as wildcard sinks: a node that accepts STRING
    # accepts anything. The reverse is NOT true — if the upstream only
    # publishes STRING and the consumer wants CNPJ, that's a real mismatch.
    return expected in (VarType.STRING, VarType.OBJECT, VarType.LIST)


def validate_graph(graph: WorkflowGraph) -> ValidationResult:
    """Run all semantic checks. Returns errors+warnings; no exception."""
    errors: list[ValidationError] = []

    if not graph.nodes:
        return ValidationResult(has_errors=False, errors=[])

    # --- Pass 1: topological walk, accumulating produced[node_id] -------

    ordered = _topological_order(graph)
    produced: dict[str, dict[str, VarType]] = {}

    # Convenience: identify the trigger node (only one expected). We use
    # this to resolve `trigger.X` paths.
    trigger_node_id: str | None = None
    for n in ordered:
        if n.type == "trigger":
            trigger_node_id = n.id
            break

    for node in ordered:
        impl = _instantiate(node)
        if impl is None:
            # Can't instantiate — most likely already caught by structural
            # validation. Skip semantic checks for this node.
            produced[node.id] = {}
            continue

        # Validate this node's requirements against what's been produced
        # by all upstream nodes (i.e. anything in `produced` so far,
        # since we walk in topological order).
        for req in impl.requires():
            err = _validate_requirement(
                req,
                node_id=node.id,
                produced=produced,
                trigger_node_id=trigger_node_id,
            )
            if err is not None:
                errors.append(err)

        # Record what this node publishes (so downstream can find it).
        # Defensive: producer can be config-dependent and raise on bad config.
        try:
            produced[node.id] = dict(impl.produces())
        except (ValueError, TypeError, KeyError, AttributeError):
            produced[node.id] = {}

    # --- Pass 2: connectivity sanity (orphan nodes) -------------------

    edge_targets = {e.target for e in graph.edges}
    for node in graph.nodes:
        if node.type == "trigger":
            continue  # roots have no incoming
        if node.id not in edge_targets:
            errors.append(
                ValidationError(
                    node_id=node.id,
                    severity="warning",
                    code="orphan_no_incoming",
                    message=(
                        f"O nó '{node.label or node.id}' não tem nenhuma "
                        "etapa anterior conectada e nunca vai executar."
                    ),
                )
            )

    has_errors = any(e.severity == "error" for e in errors)
    produced_by_node_str = {
        node_id: {k: v.value for k, v in vars_dict.items()}
        for node_id, vars_dict in produced.items()
    }
    return ValidationResult(
        has_errors=has_errors,
        errors=errors,
        produced_by_node=produced_by_node_str,
    )


def _validate_requirement(
    req: Requirement,
    *,
    node_id: str,
    produced: dict[str, dict[str, VarType]],
    trigger_node_id: str | None,
) -> ValidationError | None:
    """Check one requirement against what's been produced upstream."""
    expr = req.expr.strip()

    # --- trigger.<key>
    m = _TRIGGER_PATH_RE.match(expr)
    if m:
        key = m.group(1)
        if trigger_node_id is None:
            return ValidationError(
                node_id=node_id,
                severity="error",
                code="no_trigger_node",
                message=(
                    f"O nó '{node_id}' lê `{{{{trigger.{key}}}}}` mas o "
                    "fluxo não tem um nó de Início (trigger)."
                ),
                requirement=req.name,
                expected_type=req.type.value,
            )
        trigger_publishes = produced.get(trigger_node_id, {})
        if key not in trigger_publishes:
            return ValidationError(
                node_id=node_id,
                severity="error" if not req.optional else "warning",
                code="missing_trigger_field",
                message=(
                    f"O campo '{req.name}' do nó '{node_id}' lê "
                    f"`{{{{trigger.{key}}}}}` mas o trigger não publica "
                    f"esse campo. Campos disponíveis no trigger: "
                    f"{sorted(trigger_publishes.keys()) or '(nenhum)'}."
                ),
                requirement=req.name,
                expected_type=req.type.value,
            )
        found_type = trigger_publishes[key]
        if not _types_compatible(req.type, found_type):
            return ValidationError(
                node_id=node_id,
                severity="error",
                code="type_mismatch",
                message=(
                    f"O campo '{req.name}' espera tipo '{req.type.value}' "
                    f"mas o trigger publica '{key}' como '{found_type.value}'."
                ),
                requirement=req.name,
                expected_type=req.type.value,
                found_type=found_type.value,
            )
        return None

    # --- node.<id>.output.<key>
    m = _NODE_PATH_RE.match(expr)
    if m:
        upstream_id, key = m.group(1), m.group(2)
        if upstream_id not in produced:
            return ValidationError(
                node_id=node_id,
                severity="error",
                code="upstream_not_found",
                message=(
                    f"O nó '{node_id}' lê de "
                    f"`{{{{node.{upstream_id}.output.{key}}}}}` mas o "
                    f"nó '{upstream_id}' não está antes deste no fluxo "
                    "(ou não existe)."
                ),
                requirement=req.name,
                expected_type=req.type.value,
            )
        publishes = produced[upstream_id]
        if key not in publishes:
            return ValidationError(
                node_id=node_id,
                severity="error" if not req.optional else "warning",
                code="missing_upstream_field",
                message=(
                    f"O campo '{req.name}' do nó '{node_id}' lê "
                    f"`{{{{node.{upstream_id}.output.{key}}}}}` mas o "
                    f"nó '{upstream_id}' não publica esse campo. "
                    f"Campos disponíveis: {sorted(publishes.keys()) or '(nenhum)'}."
                ),
                requirement=req.name,
                expected_type=req.type.value,
            )
        found_type = publishes[key]
        if not _types_compatible(req.type, found_type):
            return ValidationError(
                node_id=node_id,
                severity="error",
                code="type_mismatch",
                message=(
                    f"O campo '{req.name}' do nó '{node_id}' espera "
                    f"tipo '{req.type.value}' mas o nó '{upstream_id}' "
                    f"publica '{key}' como '{found_type.value}'."
                ),
                requirement=req.name,
                expected_type=req.type.value,
                found_type=found_type.value,
            )
        return None

    # --- Path we don't recognize → silent (resolver will return None at
    # runtime; user gets a clearer signal there).
    return None


# Re-export EdgeSpec for callers that need the type alongside the validator.
__all__.append("EdgeSpec")
