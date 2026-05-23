"""PlaybookEngine — executes a playbook definition.

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

from app.agentic.memory import (
    AnalysisSession,
    attach_persistence,
    create_session,
)
from app.core.database import AsyncSessionLocal
from app.core.enums import Module, NodeRunStatus, PlaybookRunStatus
from app.shared.workflow.models.definition import PlaybookDefinition
from app.shared.workflow.models.run import PlaybookRun, PlaybookRunStep
from app.shared.workflow.nodes._base import NodeContext, NodeOutput
from app.shared.workflow.nodes.registry import NODE_TYPES, get_node_class
from app.shared.workflow.schemas.definition import EdgeSpec, NodeSpec, PlaybookGraph
from app.shared.workflow.services.resolver import (
    evaluate_edge_condition,
    resolve_templates,
)

logger = logging.getLogger(__name__)


class PlaybookEngineError(RuntimeError):
    """Engine-level error (graph cycle, missing definition, etc)."""


# ─── Graph utilities ───────────────────────────────────────────────────────


def _topological_levels(graph: PlaybookGraph) -> list[list[str]]:
    """Group node ids into levels where each level can run in parallel.

    Level 0 contains nodes with no incoming edges. Level k contains nodes
    whose dependencies are all in levels < k. Raises if a cycle is detected.
    """
    in_degree: dict[str, int] = defaultdict(int)
    deps: dict[str, list[str]] = defaultdict(list)
    all_ids = {n.id for n in graph.nodes}

    for e in graph.edges:
        if e.source not in all_ids or e.target not in all_ids:
            raise PlaybookEngineError(
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
            raise PlaybookEngineError(
                f"Workflow graph has a cycle. Remaining nodes: {sorted(remaining.keys())}"
            )
        levels.append(sorted(current))
        for nid in current:
            del remaining[nid]
        for e in graph.edges:
            if e.source in current and e.target in remaining:
                remaining[e.target] -= 1
    return levels


def _node_by_id(graph: PlaybookGraph, node_id: str) -> Any:
    """Return the NodeSpec with the given id."""
    for n in graph.nodes:
        if n.id == node_id:
            return n
    raise PlaybookEngineError(f"Node id '{node_id}' not found in graph.")


def should_skip_node(
    spec: NodeSpec,
    incoming: list[EdgeSpec],
    *,
    settled_ids: set[str],
    skipped_ids: set[str],
    eval_context: dict[str, Any],
) -> bool:
    """Decide whether a node should be SKIPPED based on incoming edges.

    Honors `spec.join_mode`:
    - "all" (default): execute only if EVERY incoming edge is satisfied
      (parent completed AND condition passes / no condition). Skip when
      any parent was skipped or any condition failed. Right semantic for
      parallel-work convergence (the common case).
    - "any": execute if at least one incoming edge is satisfied. Skip only
      when every incoming edge is blocked. Right for decision-then-converge
      patterns (one branch always skipped by mirror conditions).

    `incoming` is the list of edges with `target == spec.id`. Empty list
    means a root node — never skipped on this basis.
    """
    if not incoming:
        return False

    # Every incoming source skipped → node skipped, regardless of join_mode.
    if all(e.source in skipped_ids for e in incoming):
        return True

    if spec.join_mode == "all":
        for e in incoming:
            if e.source in skipped_ids:
                return True
            if e.source not in settled_ids:
                # Defensive: with topological execution by levels, parents
                # are always settled before the child is evaluated. If we
                # see an unsettled parent here, treat as not satisfied.
                return True
            if e.condition and not evaluate_edge_condition(e.condition, eval_context):
                return True
        return False

    # join_mode == "any": reachable if any single edge passes. Used for
    # decision-then-converge patterns where exactly one parent runs per
    # execution.
    for e in incoming:
        if e.source in skipped_ids:
            continue
        if e.source not in settled_ids:
            continue
        if not e.condition:
            return False
        if evaluate_edge_condition(e.condition, eval_context):
            return False
    return True


# ─── Run lifecycle ─────────────────────────────────────────────────────────


async def start_run(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    definition_id: UUID,
    trigger_type: str = "manual",
    trigger_data: dict[str, Any] | None = None,
    initiated_by: UUID | None = None,
) -> PlaybookRun:
    """Create a PlaybookRun row and execute it until it pauses or completes.

    Returns the (refreshed) run. The caller commits.
    """
    definition = (
        await db.execute(
            select(PlaybookDefinition).where(PlaybookDefinition.id == definition_id)
        )
    ).scalar_one_or_none()
    if definition is None:
        raise PlaybookEngineError(f"PlaybookDefinition {definition_id} not found.")

    run = PlaybookRun(
        id=uuid4(),
        tenant_id=tenant_id,
        definition_id=definition_id,
        trigger_type=trigger_type,
        trigger_data=trigger_data or {},
        status=PlaybookRunStatus.PENDING,
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
) -> PlaybookRun:
    """Resume a paused run with submitted input(s).

    `pending_inputs` is keyed by node_id. Each value is the data submitted
    for that node (e.g. the form payload of a human_input node, the analyst
    review verdict of a human_review node).
    """
    run = (
        await db.execute(select(PlaybookRun).where(PlaybookRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise PlaybookEngineError(f"PlaybookRun {run_id} not found.")
    if run.status != PlaybookRunStatus.PAUSED:
        raise PlaybookEngineError(
            f"Cannot resume run {run_id} in status {run.status.value}."
        )

    # Inject submitted inputs into context_data so the resumed node sees them.
    ctx = dict(run.context_data or {})
    for node_id, payload in pending_inputs.items():
        entry = ctx.setdefault(node_id, {})
        entry["pending_input"] = payload
    run.context_data = ctx
    run.status = PlaybookRunStatus.RUNNING
    run.paused_at = None
    await db.flush()

    definition = (
        await db.execute(
            select(PlaybookDefinition).where(PlaybookDefinition.id == run.definition_id)
        )
    ).scalar_one()

    await _execute_run(db, run, definition)
    return run


# ─── Internal executor ─────────────────────────────────────────────────────


async def _execute_run(
    db: AsyncSession,
    run: PlaybookRun,
    definition: PlaybookDefinition,
) -> None:
    """Walk the graph and execute nodes until completion or pause.

    Edge conditions are evaluated against the run context after each level.
    Whether a node executes or is SKIPPED is decided by `should_skip_node`,
    which honors the node's `join_mode` ("any" = execute when at least one
    incoming edge passes; "all" = execute only when every incoming edge
    passes). This implements n8n-style branching: a `conditional_branch`
    node typically has two outgoing edges with mirror conditions; only the
    matching branch's downstream nodes execute, the other branch is skipped.
    """
    graph = PlaybookGraph.model_validate(definition.graph)
    levels = _topological_levels(graph)

    if run.started_at is None:
        run.started_at = datetime.now(UTC)
        run.status = PlaybookRunStatus.RUNNING
        await db.flush()

    # F1.C2: cria uma AnalysisSession por execucao de run. Vive enquanto
    # _execute_run roda; nodes que invocam agentes (specialist_agent) leem
    # daqui via NodeContext.session. tool_use/result viram steps na session;
    # apos cada node, copiamos os steps deste node pra
    # workflow_node_run.input_data["tools_log"] (consumido pelo
    # AgentLiveStatus do frontend).
    #
    # Quando _execute_run e chamado em resume_run, criamos uma session
    # nova — steps anteriores ja estao persistidos em input_data.tools_log
    # dos nodes ja completos. Cross-agent scratchpad da execucao anterior
    # nao reaparece — aceitavel pra MVP; persistencia C3 trara o cenario
    # "session sobrevive entre resumes" via DB.
    session = create_session(
        tenant_id=run.tenant_id,
        started_by_user_id=run.initiated_by,
        # Workflow Credito por enquanto e o unico caller; quando outro modulo
        # registrar workflows, derivamos do `definition.module` (futuro F3).
        module=Module.CREDITO,
        context_label=f"workflow:{definition.id}:{run.id}",
    )
    # F1.C3: anexa persistencia hibrida — flush parcial apos 60s vivos
    # + flush final em end_session(). Usa AsyncSessionLocal (sessao DB
    # separada da request) pra nao colidir com `db` do caller.
    attach_persistence(session, session_factory=AsyncSessionLocal)

    # Identify nodes already completed/skipped in this run (used on resume).
    completed_rows = (
        await db.execute(
            select(PlaybookRunStep).where(
                PlaybookRunStep.run_id == run.id,
                PlaybookRunStep.status.in_(
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
            spec = _node_by_id(graph, nid)
            if should_skip_node(
                spec,
                incoming,
                settled_ids=settled_ids,
                skipped_ids=skipped_ids,
                eval_context=ctx_for_eval,
            ):
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
                _execute_node(db, run, graph, _node_by_id(graph, nid), session=session)
                for nid in to_execute
            ],
            return_exceptions=True,
        )

        for nid, result in zip(to_execute, results, strict=True):
            if isinstance(result, Exception):
                run.status = PlaybookRunStatus.FAILED
                run.error_detail = f"Node {nid} failed: {result}"
                run.completed_at = datetime.now(UTC)
                logger.exception("Node %s in run %s failed", nid, run.id)
                session.end_session()
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
            run.status = PlaybookRunStatus.PAUSED
            run.paused_at = datetime.now(UTC)
            session.end_session()
            await db.flush()
            return

    # All levels processed without pause → completed.
    run.status = PlaybookRunStatus.COMPLETED
    run.completed_at = datetime.now(UTC)
    session.end_session()
    await db.flush()


async def _persist_skipped_node(
    db: AsyncSession,
    run: PlaybookRun,
    spec: Any,
) -> None:
    """Record a SKIPPED node run (edge condition blocked) without executing."""
    now = datetime.now(UTC)
    db.add(
        PlaybookRunStep(
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
    run: PlaybookRun,
    graph: PlaybookGraph,
    spec: Any,  # NodeSpec — type hint avoided to keep import surface small
    *,
    session: AnalysisSession | None = None,
) -> NodeOutput:
    """Instantiate and execute a single node. Persist its PlaybookRunStep row.

    Resolves `{{node.X.output.field}}` and `{{trigger.field}}` templates in
    `spec.config` against the run context — n8n-style data flow between
    nodes. The resolved config is what the node implementation sees.

    `session` (F1.C2) e propagada via NodeContext.session pra nodes que
    invocam agentes. Apos a execucao, os steps que pertencem a este
    node (slice de session.steps[start:end]) sao copiados pra
    `node_run.input_data["tools_log"]` no shape AgentToolLogEntry —
    frontend `AgentLiveStatus` consome direto.
    """
    cls = get_node_class(spec.type)

    resolve_context = {
        "trigger": run.trigger_data or {},
        "node": run.context_data or {},
    }
    resolved_config = resolve_templates(spec.config or {}, resolve_context)
    impl = cls(config=resolved_config)

    started = datetime.now(UTC)
    node_run = PlaybookRunStep(
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
        node_config=resolved_config,
        session=session,
    )

    # Snapshot da posicao do session.steps antes da execucao deste node.
    # Usado pra fatiar so os steps DESTE node ao popular tools_log.
    steps_before = len(session.steps) if session is not None else 0

    try:
        output = await impl.execute(ctx, db)
    except Exception as e:
        node_run.status = NodeRunStatus.FAILED
        node_run.completed_at = datetime.now(UTC)
        node_run.error_detail = str(e)
        node_run.duration_ms = int(
            (node_run.completed_at - started).total_seconds() * 1000
        )
        # Mesmo em falha, captura o que houve no trace (alimenta o
        # AgentLiveStatus em FailedView pra mostrar onde quebrou).
        if session is not None:
            _populate_tools_log(node_run, session, steps_before)
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
    if session is not None:
        _populate_tools_log(node_run, session, steps_before)
    await db.flush()

    return output


def _populate_tools_log(
    node_run: PlaybookRunStep,
    session: AnalysisSession,
    steps_before: int,
) -> None:
    """Anexa o trace dos steps deste node em `node_run.input_data["tools_log"]`.

    Shape compativel com `AgentToolLogEntry` do frontend (iso_at, kind,
    tool_name, duration_ms, message). Frontend consome via
    `WizardWorkspace` -> `AgentLiveStatus`.
    """
    sliced = session.steps[steps_before:]
    if not sliced:
        return
    tools_log = [step.to_log_entry() for step in sliced]
    # Reatribui o dict inteiro pra garantir que o SQLAlchemy detecte
    # mutacao no JSONB (mutacao in-place pode passar despercebida).
    new_input = dict(node_run.input_data or {})
    new_input["tools_log"] = tools_log
    node_run.input_data = new_input


# ─── Cancel ───────────────────────────────────────────────────────────────


async def cancel_run(db: AsyncSession, *, run_id: UUID, tenant_id: UUID) -> None:
    """Mark a run as cancelled. Idempotent — safe to call on a finished run."""
    await db.execute(
        update(PlaybookRun)
        .where(
            PlaybookRun.id == run_id,
            PlaybookRun.tenant_id == tenant_id,
            PlaybookRun.status.in_(
                [PlaybookRunStatus.PENDING, PlaybookRunStatus.RUNNING, PlaybookRunStatus.PAUSED]
            ),
        )
        .values(
            status=PlaybookRunStatus.CANCELLED,
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
