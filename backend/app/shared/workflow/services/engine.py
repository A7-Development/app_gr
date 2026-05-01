"""WorkflowEngine — executes a workflow definition.

Responsibilities:
1. Start a run from a definition + trigger payload.
2. Walk the graph topologically, executing nodes in dependency order.
3. Handle parallel branches (siblings of a node execute concurrently).
4. Persist state at every step (`workflow_run`, `workflow_node_run`).
5. Pause when a node returns `should_pause=True` (human_input / human_review /
   document_request).
6. Resume on demand: re-execute the paused node with submitted input.

Concurrency model (MVP):
- Sequential execution of independent paths via `asyncio.gather`.
- Single Postgres connection per run (caller provides via `db`).
- Long-running nodes (specialist agents) await Anthropic streaming inside
  the same task — fine for MVP volumes, will move to APScheduler queue later.

State recovery:
- On crash, `workflow_run` stays in RUNNING and `workflow_node_run` shows
  which node was executing. A separate scheduled job will sweep stuck runs
  and either resume or fail them. Out of scope for MVP.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import NodeRunStatus, WorkflowRunStatus
from app.shared.workflow.models.definition import WorkflowDefinition
from app.shared.workflow.models.run import WorkflowNodeRun, WorkflowRun
from app.shared.workflow.nodes._base import NodeContext, NodeOutput
from app.shared.workflow.nodes.registry import NODE_TYPES, get_node_class
from app.shared.workflow.schemas.definition import WorkflowGraph
from app.shared.workflow.services.resolver import (
    evaluate_edge_condition,
    resolve_templates,
)

logger = logging.getLogger(__name__)


class WorkflowEngineError(RuntimeError):
    """Engine-level error (graph cycle, missing definition, etc)."""


# ─── Graph utilities ───────────────────────────────────────────────────────


def _topological_levels(graph: WorkflowGraph) -> list[list[str]]:
    """Group node ids into levels where each level can run in parallel.

    Level 0 contains nodes with no incoming edges. Level k contains nodes
    whose dependencies are all in levels < k. Raises if a cycle is detected.
    """
    in_degree: dict[str, int] = defaultdict(int)
    deps: dict[str, list[str]] = defaultdict(list)
    all_ids = {n.id for n in graph.nodes}

    for e in graph.edges:
        if e.source not in all_ids or e.target not in all_ids:
            raise WorkflowEngineError(
                f"Edge {e.id} references node not in graph "
                f"(source={e.source}, target={e.target})"
            )
        in_degree[e.target] += 1
        deps[e.target].append(e.source)

    # Kahn's algorithm, grouping by level.
    levels: list[list[str]] = []
    remaining = {n.id: in_degree[n.id] for n in graph.nodes}
    while remaining:
        current = [nid for nid, deg in remaining.items() if deg == 0]
        if not current:
            raise WorkflowEngineError(
                f"Workflow graph has a cycle. Remaining nodes: {sorted(remaining.keys())}"
            )
        levels.append(sorted(current))
        for nid in current:
            del remaining[nid]
        for e in graph.edges:
            if e.source in current and e.target in remaining:
                remaining[e.target] -= 1
    return levels


def _node_by_id(graph: WorkflowGraph, node_id: str) -> Any:
    """Return the NodeSpec with the given id."""
    for n in graph.nodes:
        if n.id == node_id:
            return n
    raise WorkflowEngineError(f"Node id '{node_id}' not found in graph.")


# ─── Run lifecycle ─────────────────────────────────────────────────────────


async def start_run(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    definition_id: UUID,
    trigger_type: str = "manual",
    trigger_data: dict[str, Any] | None = None,
    initiated_by: UUID | None = None,
) -> WorkflowRun:
    """Create a WorkflowRun row and execute it until it pauses or completes.

    Returns the (refreshed) run. The caller commits.
    """
    definition = (
        await db.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
        )
    ).scalar_one_or_none()
    if definition is None:
        raise WorkflowEngineError(f"WorkflowDefinition {definition_id} not found.")

    run = WorkflowRun(
        id=uuid4(),
        tenant_id=tenant_id,
        definition_id=definition_id,
        trigger_type=trigger_type,
        trigger_data=trigger_data or {},
        status=WorkflowRunStatus.PENDING,
        context_data={},
        initiated_by=initiated_by,
    )
    db.add(run)
    await db.flush()

    await _execute_run(db, run, definition)
    return run


async def resume_run(
    db: AsyncSession,
    *,
    run_id: UUID,
    pending_inputs: dict[str, dict[str, Any]],
) -> WorkflowRun:
    """Resume a paused run with submitted input(s).

    `pending_inputs` is keyed by node_id. Each value is the data submitted
    for that node (e.g. the form payload of a human_input node, the analyst
    review verdict of a human_review node).
    """
    run = (
        await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise WorkflowEngineError(f"WorkflowRun {run_id} not found.")
    if run.status != WorkflowRunStatus.PAUSED:
        raise WorkflowEngineError(
            f"Cannot resume run {run_id} in status {run.status.value}."
        )

    # Inject submitted inputs into context_data so the resumed node sees them.
    ctx = dict(run.context_data or {})
    for node_id, payload in pending_inputs.items():
        entry = ctx.setdefault(node_id, {})
        entry["pending_input"] = payload
    run.context_data = ctx
    run.status = WorkflowRunStatus.RUNNING
    run.paused_at = None
    await db.flush()

    definition = (
        await db.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.id == run.definition_id)
        )
    ).scalar_one()

    await _execute_run(db, run, definition)
    return run


# ─── Internal executor ─────────────────────────────────────────────────────


async def _execute_run(
    db: AsyncSession,
    run: WorkflowRun,
    definition: WorkflowDefinition,
) -> None:
    """Walk the graph and execute nodes until completion or pause.

    Edge conditions are evaluated against the run context after each level.
    A node is SKIPPED when ALL its incoming edges are blocked (condition
    false). This implements n8n-style branching: a `conditional_branch` node
    typically has two outgoing edges with mirror conditions; only the
    matching branch's downstream nodes execute, the other branch is skipped.
    """
    graph = WorkflowGraph.model_validate(definition.graph)
    levels = _topological_levels(graph)

    if run.started_at is None:
        run.started_at = datetime.now(UTC)
        run.status = WorkflowRunStatus.RUNNING
        await db.flush()

    # Identify nodes already completed/skipped in this run (used on resume).
    completed_rows = (
        await db.execute(
            select(WorkflowNodeRun).where(
                WorkflowNodeRun.run_id == run.id,
                WorkflowNodeRun.status.in_(
                    [NodeRunStatus.COMPLETED, NodeRunStatus.SKIPPED]
                ),
            )
        )
    ).scalars().all()
    settled_ids = {r.node_id for r in completed_rows}
    skipped_ids = {r.node_id for r in completed_rows if r.status == NodeRunStatus.SKIPPED}

    paused_anywhere = False

    for level in levels:
        pending_in_level = [nid for nid in level if nid not in settled_ids]
        if not pending_in_level:
            continue

        # Determine which nodes in this level should be SKIPPED based on
        # incoming edge conditions evaluated against the current context.
        ctx_for_eval = {
            "trigger": run.trigger_data or {},
            "node": run.context_data or {},
        }

        skip_set: set[str] = set()
        for nid in pending_in_level:
            incoming = [e for e in graph.edges if e.target == nid]
            if not incoming:
                continue  # root node — no conditions apply

            # If all incoming sources are skipped, this node is also skipped.
            if all(e.source in skipped_ids for e in incoming):
                skip_set.add(nid)
                continue

            # If any incoming edge passes (no condition or condition true),
            # the node is reachable. Otherwise skip.
            reachable = False
            for e in incoming:
                if e.source in skipped_ids:
                    continue
                if e.source not in settled_ids:
                    # Source hasn't run yet — not actually a current edge to
                    # evaluate (shouldn't happen with topological order, but
                    # safe fallback: assume not reachable yet).
                    continue
                if not e.condition:
                    reachable = True
                    break
                if evaluate_edge_condition(e.condition, ctx_for_eval):
                    reachable = True
                    break
            if not reachable:
                skip_set.add(nid)

        # Apply skips first (no execution, just persist + record).
        for nid in skip_set:
            await _persist_skipped_node(db, run, _node_by_id(graph, nid))
            settled_ids.add(nid)
            skipped_ids.add(nid)

        # Execute the rest in parallel.
        to_execute = [nid for nid in pending_in_level if nid not in skip_set]
        if not to_execute:
            await db.flush()
            continue

        results = await asyncio.gather(
            *[
                _execute_node(db, run, graph, _node_by_id(graph, nid))
                for nid in to_execute
            ],
            return_exceptions=True,
        )

        for nid, result in zip(to_execute, results, strict=True):
            if isinstance(result, Exception):
                run.status = WorkflowRunStatus.FAILED
                run.error_detail = f"Node {nid} failed: {result}"
                run.completed_at = datetime.now(UTC)
                logger.exception("Node %s in run %s failed", nid, run.id)
                await db.flush()
                return
            output: NodeOutput = result
            ctx_entry = dict(run.context_data.get(nid, {}))
            ctx_entry["output"] = output.data
            ctx_entry["status_hint"] = output.status_hint
            ctx_entry.pop("pending_input", None)
            new_ctx = dict(run.context_data)
            new_ctx[nid] = ctx_entry
            run.context_data = new_ctx
            settled_ids.add(nid)
            if output.should_pause:
                paused_anywhere = True

        await db.flush()

        if paused_anywhere:
            run.status = WorkflowRunStatus.PAUSED
            run.paused_at = datetime.now(UTC)
            await db.flush()
            return

    # All levels processed without pause → completed.
    run.status = WorkflowRunStatus.COMPLETED
    run.completed_at = datetime.now(UTC)
    await db.flush()


async def _persist_skipped_node(
    db: AsyncSession,
    run: WorkflowRun,
    spec: Any,
) -> None:
    """Record a SKIPPED node run (edge condition blocked) without executing."""
    now = datetime.now(UTC)
    db.add(
        WorkflowNodeRun(
            id=uuid4(),
            run_id=run.id,
            tenant_id=run.tenant_id,
            node_id=spec.id,
            node_type=spec.type,
            status=NodeRunStatus.SKIPPED,
            input_data={},
            output_data={"reason": "skipped — incoming edge condition not met"},
            started_at=now,
            completed_at=now,
            duration_ms=0,
            attempt_number=1,
        )
    )
    await db.flush()


async def _execute_node(
    db: AsyncSession,
    run: WorkflowRun,
    graph: WorkflowGraph,
    spec: Any,  # NodeSpec — type hint avoided to keep import surface small
) -> NodeOutput:
    """Instantiate and execute a single node. Persist its WorkflowNodeRun row.

    Resolves `{{node.X.output.field}}` and `{{trigger.field}}` templates in
    `spec.config` against the run context — n8n-style data flow between
    nodes. The resolved config is what the node implementation sees.
    """
    cls = get_node_class(spec.type)

    resolve_context = {
        "trigger": run.trigger_data or {},
        "node": run.context_data or {},
    }
    resolved_config = resolve_templates(spec.config or {}, resolve_context)
    impl = cls(config=resolved_config)

    started = datetime.now(UTC)
    node_run = WorkflowNodeRun(
        id=uuid4(),
        run_id=run.id,
        tenant_id=run.tenant_id,
        node_id=spec.id,
        node_type=spec.type,
        status=NodeRunStatus.RUNNING,
        input_data=resolved_config,
        output_data={},
        started_at=started,
        attempt_number=1,
    )
    db.add(node_run)
    await db.flush()

    ctx = NodeContext(
        run_id=run.id,
        tenant_id=run.tenant_id,
        node_id=spec.id,
        initiated_by=run.initiated_by,
        previous_outputs=run.context_data or {},
        trigger_data=run.trigger_data or {},
    )

    try:
        output = await impl.execute(ctx, db)
    except Exception as e:
        node_run.status = NodeRunStatus.FAILED
        node_run.completed_at = datetime.now(UTC)
        node_run.error_detail = str(e)
        node_run.duration_ms = int(
            (node_run.completed_at - started).total_seconds() * 1000
        )
        await db.flush()
        raise

    completed = datetime.now(UTC)
    node_run.output_data = output.data
    node_run.completed_at = completed
    node_run.duration_ms = int((completed - started).total_seconds() * 1000)
    node_run.tokens_input = output.tokens_input
    node_run.tokens_output = output.tokens_output
    node_run.cost_brl = output.cost_brl
    node_run.status = (
        NodeRunStatus.WAITING_INPUT if output.should_pause else NodeRunStatus.COMPLETED
    )
    await db.flush()

    return output


# ─── Cancel ───────────────────────────────────────────────────────────────


async def cancel_run(db: AsyncSession, *, run_id: UUID, tenant_id: UUID) -> None:
    """Mark a run as cancelled. Idempotent — safe to call on a finished run."""
    await db.execute(
        update(WorkflowRun)
        .where(
            WorkflowRun.id == run_id,
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.status.in_(
                [WorkflowRunStatus.PENDING, WorkflowRunStatus.RUNNING, WorkflowRunStatus.PAUSED]
            ),
        )
        .values(
            status=WorkflowRunStatus.CANCELLED,
            completed_at=datetime.now(UTC),
        )
    )


# ─── Catalog (for the visual editor) ──────────────────────────────────────


def list_node_types_for_editor() -> list[dict[str, Any]]:
    """Return node types with their metadata, suitable for the editor palette.

    Includes `available=False` types so they appear as "em breve". Also
    exposes `config_schema` so the Inspector can render the right form
    fields when a node is selected.
    """
    return [
        {
            "type": meta.type,
            "label": meta.label,
            "category": meta.category,
            "description": meta.description,
            "available": meta.available,
            "icon": meta.icon,
            "config_schema": [dict(f) for f in meta.config_schema],
        }
        for meta in NODE_TYPES.values()
    ]
