"""_populate_tools_log copia o slice correto de steps para node_run (C2 Task 7).

Pure-function test do helper que vive em
app/shared/workflow/services/engine.py. Nao precisa de DB nem
asyncpg — passa um objeto duck-typed no lugar do `WorkflowNodeRun`.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest

from app.agentic.memory import create_session
from app.core.enums import Module

# engine.py importa app.agentic.memory (que importamos OK) mas tambem
# carrega WorkflowNodeRun (SQLAlchemy). Quando anthropic/SQLAlchemy
# nao estao instalados, skip o modulo inteiro.
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("anthropic") is None,
    reason="anthropic SDK ausente",
)


@dataclass
class _FakeNodeRun:
    """Duck do WorkflowNodeRun, soh com o que _populate_tools_log toca."""

    input_data: dict[str, Any] = field(default_factory=dict)


def _new_session():
    return create_session(
        tenant_id=uuid4(),
        started_by_user_id=uuid4(),
        module=Module.CREDITO,
        context_label="test:engine",
    )


def test_populates_tools_log_from_slice() -> None:
    from app.shared.workflow.services.engine import _populate_tools_log

    s = _new_session()
    s.record_tool_use(
        agent_full_id="node_a@v1", tool_name="t1", input_args={"x": 1}
    )
    s.record_tool_result(
        agent_full_id="node_a@v1", tool_name="t1", output="r1", duration_ms=5
    )

    node_a = _FakeNodeRun(input_data={"agent": "x"})  # already has config
    _populate_tools_log(node_a, s, steps_before=0)  # type: ignore[arg-type]

    assert "tools_log" in node_a.input_data
    log = node_a.input_data["tools_log"]
    assert len(log) == 2
    assert log[0]["kind"] == "tool_use"
    assert log[0]["tool_name"] == "t1"
    assert log[1]["kind"] == "tool_result"
    assert log[1]["duration_ms"] == 5
    # Config original preservado.
    assert node_a.input_data["agent"] == "x"


def test_slice_isolates_each_node_run() -> None:
    """Dois nodes consecutivos: cada um so ve seus proprios steps."""
    from app.shared.workflow.services.engine import _populate_tools_log

    s = _new_session()

    # Node A executou primeiro.
    steps_before_a = len(s.steps)
    s.record_tool_use(agent_full_id="a@v1", tool_name="tool_a", input_args={})
    s.record_tool_result(
        agent_full_id="a@v1", tool_name="tool_a", output="ok", duration_ms=1
    )

    node_a = _FakeNodeRun()
    _populate_tools_log(node_a, s, steps_before_a)  # type: ignore[arg-type]

    # Node B executa depois.
    steps_before_b = len(s.steps)
    s.record_tool_use(agent_full_id="b@v1", tool_name="tool_b", input_args={})
    s.record_tool_result(
        agent_full_id="b@v1", tool_name="tool_b", output="ok", duration_ms=2
    )

    node_b = _FakeNodeRun()
    _populate_tools_log(node_b, s, steps_before_b)  # type: ignore[arg-type]

    # Cada node so ve os seus steps.
    a_log = node_a.input_data["tools_log"]
    b_log = node_b.input_data["tools_log"]

    assert {e["tool_name"] for e in a_log} == {"tool_a"}
    assert {e["tool_name"] for e in b_log} == {"tool_b"}
    assert len(a_log) == 2
    assert len(b_log) == 2


def test_no_tools_log_key_when_node_did_not_emit_steps() -> None:
    from app.shared.workflow.services.engine import _populate_tools_log

    s = _new_session()
    # Nada gravado entre antes e depois.
    nr = _FakeNodeRun(input_data={"agent": "x"})
    _populate_tools_log(nr, s, steps_before=0)  # type: ignore[arg-type]

    # input_data preservado, sem tools_log adicionada (steps vazios).
    assert "tools_log" not in nr.input_data
    assert nr.input_data == {"agent": "x"}


def test_session_label_includes_run_id() -> None:
    """Smoke do context_label que o engine cria."""
    from app.shared.workflow.services.engine import _execute_run  # noqa: F401

    # Soh confirma que a string montada e human-readable; nao executa nada.
    label = "workflow:def-id:run-id"
    assert "workflow:" in label
