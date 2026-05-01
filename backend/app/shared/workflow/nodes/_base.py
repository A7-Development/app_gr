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
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


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

    @abstractmethod
    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        """Run this node and return its output.

        Implementations may persist auxiliary rows (e.g. document records),
        but the engine handles `workflow_node_run` itself based on the
        returned `NodeOutput`.
        """
