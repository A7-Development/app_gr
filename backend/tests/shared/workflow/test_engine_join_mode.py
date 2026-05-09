"""Engine helper — should_skip_node honors NodeSpec.join_mode.

Pure-function tests against the helper extracted from `_execute_run`.
No DB or async required: the function takes settled/skipped sets and an
eval context, returns bool.

Cases covered:
- join=any (default) is permissive: one good parent is enough.
- join=all is strict: any blocked parent skips the node.
- conditions are honored under both modes.
- a root node (no incoming) is never skipped on this basis.
- when every parent was skipped, the node skips regardless of mode.
"""

from __future__ import annotations

from app.shared.workflow.schemas.definition import EdgeSpec, NodeSpec
from app.shared.workflow.services.engine import should_skip_node


def _spec(node_id: str, *, join_mode: str = "any") -> NodeSpec:
    return NodeSpec(id=node_id, type="noop", join_mode=join_mode)  # type: ignore[arg-type]


def _edge(eid: str, source: str, target: str, condition: str | None = None) -> EdgeSpec:
    return EdgeSpec(id=eid, source=source, target=target, condition=condition)


# ─── No incoming (root) ────────────────────────────────────────────────────


def test_root_node_is_never_skipped() -> None:
    spec = _spec("trigger")
    assert should_skip_node(
        spec,
        incoming=[],
        settled_ids=set(),
        skipped_ids=set(),
        eval_context={"trigger": {}, "node": {}},
    ) is False


# ─── join=any (default) ────────────────────────────────────────────────────


def test_any_one_parent_skipped_one_ok_executes() -> None:
    """join=any with [skipped, ok] → reachable via the ok parent."""
    spec = _spec("financial", join_mode="any")
    incoming = [_edge("e1", "a", "financial"), _edge("e2", "b", "financial")]
    assert should_skip_node(
        spec,
        incoming=incoming,
        settled_ids={"a", "b"},
        skipped_ids={"a"},
        eval_context={"trigger": {}, "node": {"b": {"output": {}}}},
    ) is False


def test_any_all_parents_skipped_node_skips() -> None:
    spec = _spec("financial", join_mode="any")
    incoming = [_edge("e1", "a", "financial"), _edge("e2", "b", "financial")]
    assert should_skip_node(
        spec,
        incoming=incoming,
        settled_ids={"a", "b"},
        skipped_ids={"a", "b"},
        eval_context={"trigger": {}, "node": {}},
    ) is True


def test_any_one_condition_passes_executes() -> None:
    spec = _spec("financial", join_mode="any")
    incoming = [
        _edge("e1", "a", "financial", condition='{{node.a.output.score}} > 700'),
        _edge("e2", "b", "financial", condition='{{node.b.output.score}} > 700'),
    ]
    eval_ctx = {
        "trigger": {},
        "node": {
            "a": {"output": {"score": 600}},  # condition fails
            "b": {"output": {"score": 800}},  # condition passes
        },
    }
    assert should_skip_node(
        spec,
        incoming=incoming,
        settled_ids={"a", "b"},
        skipped_ids=set(),
        eval_context=eval_ctx,
    ) is False


def test_any_all_conditions_fail_node_skips() -> None:
    spec = _spec("financial", join_mode="any")
    incoming = [
        _edge("e1", "a", "financial", condition='{{node.a.output.score}} > 700'),
        _edge("e2", "b", "financial", condition='{{node.b.output.score}} > 700'),
    ]
    eval_ctx = {
        "trigger": {},
        "node": {
            "a": {"output": {"score": 600}},
            "b": {"output": {"score": 500}},
        },
    }
    assert should_skip_node(
        spec,
        incoming=incoming,
        settled_ids={"a", "b"},
        skipped_ids=set(),
        eval_context=eval_ctx,
    ) is True


# ─── join=all ──────────────────────────────────────────────────────────────


def test_all_one_parent_skipped_node_skips() -> None:
    """The flagship case: serasa OK + processos skipped → financial must skip."""
    spec = _spec("financial", join_mode="all")
    incoming = [
        _edge("e1", "serasa", "financial"),
        _edge("e2", "processos", "financial"),
    ]
    assert should_skip_node(
        spec,
        incoming=incoming,
        settled_ids={"serasa", "processos"},
        skipped_ids={"processos"},
        eval_context={"trigger": {}, "node": {"serasa": {"output": {}}}},
    ) is True


def test_all_both_parents_ok_no_conditions_executes() -> None:
    spec = _spec("financial", join_mode="all")
    incoming = [
        _edge("e1", "serasa", "financial"),
        _edge("e2", "processos", "financial"),
    ]
    assert should_skip_node(
        spec,
        incoming=incoming,
        settled_ids={"serasa", "processos"},
        skipped_ids=set(),
        eval_context={
            "trigger": {},
            "node": {
                "serasa": {"output": {}},
                "processos": {"output": {}},
            },
        },
    ) is False


def test_all_one_condition_fails_node_skips() -> None:
    spec = _spec("financial", join_mode="all")
    incoming = [
        _edge("e1", "serasa", "financial", condition='{{node.serasa.output.score}} > 700'),
        _edge("e2", "processos", "financial"),
    ]
    eval_ctx = {
        "trigger": {},
        "node": {
            "serasa": {"output": {"score": 600}},  # fails
            "processos": {"output": {}},
        },
    }
    assert should_skip_node(
        spec,
        incoming=incoming,
        settled_ids={"serasa", "processos"},
        skipped_ids=set(),
        eval_context=eval_ctx,
    ) is True


def test_all_both_conditions_pass_executes() -> None:
    spec = _spec("financial", join_mode="all")
    incoming = [
        _edge("e1", "serasa", "financial", condition='{{node.serasa.output.score}} > 700'),
        _edge("e2", "processos", "financial", condition='{{node.processos.output.qtd}} < 10'),
    ]
    eval_ctx = {
        "trigger": {},
        "node": {
            "serasa": {"output": {"score": 800}},
            "processos": {"output": {"qtd": 3}},
        },
    }
    assert should_skip_node(
        spec,
        incoming=incoming,
        settled_ids={"serasa", "processos"},
        skipped_ids=set(),
        eval_context=eval_ctx,
    ) is False


def test_default_join_mode_is_all() -> None:
    """A NodeSpec without explicit join_mode defaults to 'all' — the safer
    semantic for parallel-work convergence (the common case)."""
    spec = NodeSpec(id="financial", type="noop")
    assert spec.join_mode == "all"
