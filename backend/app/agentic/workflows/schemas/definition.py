"""Pydantic schemas for WorkflowDefinition API + graph shape.

The `graph` JSONB column on `workflow_definition` is validated against
`WorkflowGraph` on every write. This guarantees that any consumer reading
from `definition.graph` can trust the structure without revalidating.

Node `config` is a free-form dict — each node type defines its own config
schema, validated by the engine when instantiating the node implementation
(see `app/shared/workflow/nodes/`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import WorkflowStatus

JoinMode = Literal["any", "all"]


class NodeSpec(BaseModel):
    """One node in the workflow graph."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., description="Node type (e.g. 'specialist_agent', 'bureau_query')")
    label: str | None = Field(None, description="Human-readable label for the editor")

    # Node-specific configuration. Validated by each node's executor.
    config: dict[str, Any] = Field(default_factory=dict)

    # Position on the visual canvas (x, y in pixels). Optional — engine
    # ignores it; only the editor uses it.
    position: dict[str, float] | None = None

    # Fan-in semantics when the node has 2+ incoming edges.
    # "all" (default): node executes only if EVERY incoming edge is
    #   satisfied (all parents completed AND each condition passes / has
    #   no condition). If any parent was skipped or its condition failed,
    #   the node skips. Right default for parallel-work convergence — the
    #   common case in this domain.
    # "any": node executes if at least one incoming edge is satisfied.
    #   Use this for the "decision → divergent branches → convergence at
    #   a terminal step" pattern, where exactly one parent runs per execution
    #   (the others are skipped by mirror conditions on a conditional_branch).
    join_mode: JoinMode = "all"


class EdgeSpec(BaseModel):
    """A directed edge between two nodes."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=128)
    source: str = Field(..., description="ID of the source node")
    target: str = Field(..., description="ID of the target node")

    # Ancoras visuais do React Flow (qual lado do node a edge sai/entra:
    # "top"/"right"/"bottom"/"left"). Puramente COSMETICO — o engine/resolver
    # ignoram (so usam source/target/condition). Persistir preserva o layout
    # que o usuario desenhou; sem isso, ao recarregar todas as edges caem no
    # primeiro handle ("top"). Null = deixa o React Flow escolher o default.
    source_handle: str | None = None
    target_handle: str | None = None

    # Optional condition for branching (evaluated by the resolver).
    # Example: "{{node.score.output.value}} >= 700"
    condition: str | None = None


class WorkflowGraph(BaseModel):
    """The full graph: nodes + edges + metadata."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[NodeSpec]
    edges: list[EdgeSpec]

    @field_validator("nodes")
    @classmethod
    def _node_ids_unique(cls, v: list[NodeSpec]) -> list[NodeSpec]:
        ids = [n.id for n in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Node IDs must be unique within a workflow.")
        return v

    @field_validator("edges")
    @classmethod
    def _edge_ids_unique(cls, v: list[EdgeSpec]) -> list[EdgeSpec]:
        ids = [e.id for e in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Edge IDs must be unique within a workflow.")
        return v


class WorkflowDefinitionCreate(BaseModel):
    """Input to create a new workflow definition (v1).

    When `clone_from` is provided, the new workflow's graph is copied from
    that definition (must be visible to the caller — own tenant or starter
    Strata). The user only provides `name` + optional `description`; the
    `graph` and `category` come from the source.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    category: str | None = Field(None, min_length=1, max_length=64)
    graph: WorkflowGraph | None = None
    clone_from: UUID | None = None


class WorkflowActivatePayload(BaseModel):
    """Input to activate a specific definition as the tenant's current version."""

    model_config = ConfigDict(extra="forbid")

    definition_id: UUID


class WorkflowDefinitionUpdate(BaseModel):
    """Input to update a definition. Creates a new version row."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    graph: WorkflowGraph


class WorkflowDefinitionRead(BaseModel):
    """API output for a workflow definition row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID | None
    name: str
    version: int
    description: str | None
    category: str
    graph: dict[str, Any]
    status: WorkflowStatus
    created_by: UUID | None
    created_at: datetime
    archived_at: datetime | None
