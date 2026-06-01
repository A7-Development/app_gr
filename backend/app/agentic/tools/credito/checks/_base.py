"""Check registry — deterministic credit checks (pure functions, no LLM).

A *check* is the deterministic counterpart of a specialist agent: it reads
the persisted dossier graph (companies, persons, policy) and returns a
`CheckResult` — `passed` (for gate routing) plus structured `flags` (the
cross-check inconsistencies that are the product's unit of value, handoff §1)
plus the inputs/output for the audit trail.

Checks NEVER write to the DB and NEVER call an LLM. Persisting the
`decision_log` entry and the `red_flag` rows is the job of the
`deterministic_check` node that runs the check — keeping checks pure and
trivially testable.

Checks register themselves via `@register_check`; the `deterministic_check`
node resolves one by name from `CHECK_REGISTRY` (analogous to `NODE_TYPES`).
The manager picks which check a node runs in the visual builder.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True)
class CheckContext:
    """What a check receives. Read-only access to the dossier graph + config."""

    db: AsyncSession
    tenant_id: UUID
    dossier_id: UUID
    # Resolved node config (knobs like policy_name, tolerance_pct).
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FlagSpec:
    """A structured red flag a check wants raised (handoff §1 provenance).

    Persisted by the node into `credit_dossier_red_flag` and linked to the
    `decision_log` entry. `provenance` follows the canonical shape documented
    on the model (check_type / source / field / expected_value / actual_value
    / comparisons / detail).
    """

    severity: str  # 'critical' | 'important' | 'informational'
    title: str
    description: str
    evidence: str
    check_type: str
    provenance: dict[str, Any]
    section: str | None = None


@dataclass(slots=True)
class CheckResult:
    """Pure output of a check. Side effects are applied by the node."""

    passed: bool
    flags: list[FlagSpec] = field(default_factory=list)
    # Recorded in decision_log.inputs_ref / .output (must be JSON-safe).
    decision_inputs: dict[str, Any] = field(default_factory=dict)
    decision_output: dict[str, Any] = field(default_factory=dict)
    summary: str = ""


CheckFn = Callable[[CheckContext], Awaitable[CheckResult]]


@dataclass(frozen=True, slots=True)
class CheckMeta:
    """Metadata for a registered check — exposed to the builder."""

    name: str
    fn: CheckFn
    label: str
    description: str


CHECK_REGISTRY: dict[str, CheckMeta] = {}


def register_check(
    *, name: str, label: str, description: str
) -> Callable[[CheckFn], CheckFn]:
    """Register a deterministic check under `name`."""

    def deco(fn: CheckFn) -> CheckFn:
        if name in CHECK_REGISTRY:
            raise ValueError(f"check '{name}' ja registrado")
        CHECK_REGISTRY[name] = CheckMeta(
            name=name, fn=fn, label=label, description=description
        )
        return fn

    return deco


def get_check(name: str) -> CheckMeta:
    meta = CHECK_REGISTRY.get(name)
    if meta is None:
        raise ValueError(
            f"check '{name}' nao registrado. Conhecidos: {sorted(CHECK_REGISTRY)}"
        )
    return meta


def list_checks() -> list[dict[str, str]]:
    """Catalog for the builder (a check picker can fetch this)."""
    return [
        {"name": m.name, "label": m.label, "description": m.description}
        for m in CHECK_REGISTRY.values()
    ]
