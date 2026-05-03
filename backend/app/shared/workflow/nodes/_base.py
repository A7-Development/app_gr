"""BaseNode — interface every node type implementation must follow.

A node receives:
- its `config` dict from the workflow graph (e.g. {"agent": "social_contract_analyst"})
- a `NodeContext` with the run id, tenant id, and accumulated outputs from
  previous nodes (for resolving `{{node.X.output.field}}` references)
- a database session

It returns a `NodeOutput`:
- `data`: structured output to be persisted on `workflow_node_run.output_data`
  and exposed to downstream nodes
- `should_pause`: True if the node's completion requires waiting for human
  input (used by human_input, human_review, document_request)
- `tokens_input/tokens_output/cost_brl`: optional cost metering when the
  node called a LLM

Errors are raised — the engine catches them and persists with status FAILED.

Semantic typing (Fase 2 — 2026-05-02):

Each node type also declares its data contract via two methods:

- `produces() -> dict[str, VarType]`: the typed variables this node EXPOSES
  in `output.data` after a successful execution. Downstream nodes can refer
  to them via `{{node.<this_id>.output.<key>}}`.

- `requires() -> list[Requirement]`: the typed variables this node CONSUMES.
  The graph validator inspects each `Requirement.expr` (e.g.
  `{{node.human_input_x.output.cnpj}}`) and confirms that some upstream node
  produces a compatible type at that path.

The same node TYPE can produce/require different variables depending on its
config — `bureau_query[serasa_pj]` requires `cnpj` (or `cpf`), but a future
`bureau_query[boa_vista_pf]` would require `cpf` only. So `produces` and
`requires` read `self.config` and return per-instance contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class VarType(StrEnum):
    """Semantic types of variables that flow between nodes.

    Used by `BaseNode.produces()` / `requires()` and the graph validator.
    Compatibility is per-name match for the MVP — i.e. a `Requirement(name=
    'cnpj', type=CNPJ)` is satisfied by any upstream `produces()` entry
    where the value is `VarType.CNPJ`. Future iterations may add subtype
    coercions (e.g. STRING accepts CNPJ).
    """

    STRING = "string"          # generic free text
    CPF = "cpf"                # 11 digits, doc PF
    CNPJ = "cnpj"              # 14 digits, doc PJ
    EMAIL = "email"
    PHONE = "phone"
    DATE = "date"              # ISO YYYY-MM-DD
    DATETIME = "datetime"      # ISO 8601
    NUMBER = "number"          # any numeric (int or float)
    MONEY_BRL = "money_brl"    # decimal monetary in BRL
    SCORE = "score"            # 0..1000 typically
    BOOLEAN = "boolean"
    URL = "url"
    UUID_T = "uuid"            # UUID string (collides with stdlib UUID — suffix _T)
    FILE = "file"              # filesystem ref / binary blob descriptor
    OBJECT = "object"          # nested dict, escape hatch
    LIST = "list"              # list of values, escape hatch


@dataclass(slots=True, frozen=True)
class Requirement:
    """One typed variable a node needs in order to execute.

    `expr` is the dotted path the node reads from at runtime (matches the
    template syntax used in `config` resolution — e.g. `trigger.cnpj` or
    `node.human_input_f0ugxb.output.cnpj`). `optional=True` means absent
    upstream is a warning, not an error.
    """

    name: str             # human-readable label (shown in error msg)
    type: VarType         # expected semantic type
    expr: str             # dotted path the runtime resolves
    optional: bool = False


@dataclass(slots=True)
class NodeContext:
    """Runtime context passed to every node execution."""

    run_id: UUID
    tenant_id: UUID
    node_id: str               # id of THIS node within the graph
    initiated_by: UUID | None  # user that triggered the run
    # Accumulated outputs of previously-completed nodes:
    #   { "<other_node_id>": { "output": {...}, "duration_ms": int } }
    previous_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Free-form trigger payload (e.g. dossier_id, user-provided input).
    trigger_data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NodeOutput:
    """Result of executing one node."""

    data: dict[str, Any]
    should_pause: bool = False
    tokens_input: int = 0
    tokens_output: int = 0
    cost_brl: Decimal = Decimal("0")
    # Optional: a human-readable status hint (rendered in the UI).
    status_hint: str | None = None


class BaseNode(ABC):
    """Abstract base for every node type.

    Subclasses implement `execute()` and may override `validate_config()`.
    The engine instantiates one BaseNode subclass per node in the graph and
    calls `.execute()` exactly once per attempt.
    """

    #: Type identifier as it appears in the workflow graph JSON.
    type: str = ""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.validate_config()

    def validate_config(self) -> None:
        """Validate `self.config` against this node type's expectations.

        Default: no-op. Subclasses that have required keys should override.
        Raise `ValueError` on invalid config.
        """

    def produces(self) -> dict[str, VarType]:
        """Return the typed variables this node exposes in `output.data`.

        Keys correspond to fields in the dict returned by `execute().data`,
        accessible downstream as `{{node.<this_id>.output.<key>}}`.
        Default: nothing — most nodes that have outputs override.
        """
        return {}

    def requires(self) -> list[Requirement]:
        """Return the typed variables this node consumes from upstream.

        Each requirement has an `expr` (dotted path, e.g. `trigger.cnpj`
        or `node.<id>.output.<field>`) that the runtime resolver reads.
        The graph validator checks the path resolves to an upstream
        producer of the matching type.

        Default: nothing — pure-config nodes (`trigger`, `notification`)
        usually don't consume upstream data.
        """
        return []

    @abstractmethod
    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        """Run this node and return its output.

        Implementations may persist auxiliary rows (e.g. document records),
        but the engine handles `workflow_node_run` itself based on the
        returned `NodeOutput`.
        """
