"""Unit tests — AnalysisSession + Scratchpad + StepCache + memory tools (C1).

Covers Phase 1 foundation of the session memory layer (CLAUDE.md sec 19.11).
No DB, no asyncpg — pure in-process behavior.
"""

from __future__ import annotations

import time
from uuid import uuid4

import pytest

from app.agentic.memory import (
    AnalysisSession,
    SessionStep,
    StepKind,
    create_session,
)
from app.agentic.memory.scratchpad import Scratchpad
from app.agentic.memory.step_cache import StepCache
from app.agentic.memory.tools import make_memory_tools
from app.agentic.tools._base import AgentTool, register_tool
from app.agentic.tools.registry import ToolRegistry
from app.core.enums import Module, Permission

# ─── Factory ──────────────────────────────────────────────────────────────


def _new_session(*, context_label: str = "test:session") -> AnalysisSession:
    return create_session(
        tenant_id=uuid4(),
        started_by_user_id=uuid4(),
        module=Module.CREDITO,
        context_label=context_label,
    )


# ─── Lifecycle ────────────────────────────────────────────────────────────


def test_create_session_populates_required_fields() -> None:
    s = _new_session(context_label="dossier:abc")

    assert s.id is not None
    assert s.tenant_id is not None
    assert s.module == Module.CREDITO
    assert s.context_label == "dossier:abc"
    assert s.ended_at is None
    assert s.steps == []
    assert isinstance(s.scratchpad, Scratchpad)
    assert isinstance(s.step_cache, StepCache)
    assert s.kv_store == {}


def test_end_session_is_idempotent() -> None:
    s = _new_session()

    s.end_session()
    first_end = s.ended_at
    assert first_end is not None

    s.end_session()
    assert s.ended_at == first_end  # second call no-op


def test_session_duration_grows_then_freezes_on_end() -> None:
    s = _new_session()

    time.sleep(0.05)
    d1 = s.duration_seconds
    assert d1 >= 0.05

    s.end_session()
    time.sleep(0.05)
    d2 = s.duration_seconds
    # Apos end_session, duration nao deve crescer mais.
    assert d2 == pytest.approx(d1, abs=0.01)


# ─── Step recording ───────────────────────────────────────────────────────


def test_record_tool_use_creates_step() -> None:
    s = _new_session()

    step = s.record_tool_use(
        agent_full_id="credito.financial_analyst@v1",
        tool_name="read_dossier_section",
        input_args={"section_id": "financial"},
    )

    assert isinstance(step, SessionStep)
    assert step.kind == StepKind.TOOL_USE
    assert step.agent_full_id == "credito.financial_analyst@v1"
    assert step.tool_name == "read_dossier_section"
    assert step.input_json == {"section_id": "financial"}
    assert step.step_index == 0
    assert step.message == "-> read_dossier_section"


def test_record_tool_result_marks_cache_when_set() -> None:
    s = _new_session()

    s.record_tool_use(
        agent_full_id="a@v1", tool_name="t", input_args={"x": 1}
    )
    step = s.record_tool_result(
        agent_full_id="a@v1",
        tool_name="t",
        output="payload",
        duration_ms=42,
        from_cache=True,
    )

    assert step.kind == StepKind.TOOL_RESULT
    assert step.duration_ms == 42
    assert step.output_json == {"text": "payload"}
    assert step.message is not None
    assert "[cache]" in step.message


def test_record_error_truncates_long_message() -> None:
    s = _new_session()

    long_err = "x" * 5000
    step = s.record_error(
        agent_full_id="a@v1",
        tool_name="failing",
        error=long_err,
    )

    assert step.kind == StepKind.ERROR
    assert step.error == long_err  # full text preserved in payload
    assert step.message is not None
    assert len(step.message) <= 250  # truncated in message preview


def test_step_index_monotonic_across_kinds() -> None:
    s = _new_session()

    s.record_tool_use(agent_full_id="a@v1", tool_name="t", input_args={})
    s.record_tool_result(
        agent_full_id="a@v1", tool_name="t", output="ok", duration_ms=1
    )
    s.record_observation(agent_full_id="a@v1", message="done")
    s.record_error(agent_full_id="a@v1", tool_name=None, error="oops")

    indices = [step.step_index for step in s.steps]
    assert indices == [0, 1, 2, 3]


def test_record_scratchpad_write_preserves_full_text_in_output() -> None:
    s = _new_session()

    long_text = "a" * 3000
    step = s.record_scratchpad_write(
        agent_full_id="a@v1", text=long_text
    )

    assert step.kind == StepKind.SCRATCHPAD_WRITE
    assert step.output_json is not None
    assert step.output_json["text"] == long_text  # capped at 4000, fits
    assert step.message is not None
    assert len(step.message) <= 250


def test_steps_for_agent_filters() -> None:
    s = _new_session()

    s.record_tool_use(
        agent_full_id="agent_a@v1", tool_name="t1", input_args={}
    )
    s.record_tool_use(
        agent_full_id="agent_b@v1", tool_name="t2", input_args={}
    )
    s.record_tool_use(
        agent_full_id="agent_a@v1", tool_name="t3", input_args={}
    )

    a_steps = s.steps_for_agent("agent_a@v1")
    assert len(a_steps) == 2
    assert all(step.agent_full_id == "agent_a@v1" for step in a_steps)
    assert [step.tool_name for step in a_steps] == ["t1", "t3"]


def test_to_log_entry_shape_matches_frontend_contract() -> None:
    # Frontend AgentToolLogEntry: iso_at, kind, tool_name, duration_ms, message
    s = _new_session()
    step = s.record_tool_result(
        agent_full_id="a@v1",
        tool_name="ref_calc",
        output="42",
        duration_ms=15,
    )

    entry = step.to_log_entry()
    assert set(entry.keys()) == {
        "iso_at",
        "kind",
        "tool_name",
        "duration_ms",
        "message",
    }
    assert entry["kind"] == "tool_result"
    assert entry["tool_name"] == "ref_calc"
    assert entry["duration_ms"] == 15
    assert isinstance(entry["iso_at"], str)  # ISO string


# ─── Callbacks ────────────────────────────────────────────────────────────


def test_on_step_callback_fires_for_every_record() -> None:
    s = _new_session()
    captured: list[SessionStep] = []
    s._on_step = captured.append

    s.record_tool_use(
        agent_full_id="a@v1", tool_name="t", input_args={}
    )
    s.record_observation(agent_full_id="a@v1", message="done")

    assert len(captured) == 2
    assert captured[0].kind == StepKind.TOOL_USE
    assert captured[1].kind == StepKind.OBSERVATION


def test_on_step_callback_exception_does_not_break_recording() -> None:
    s = _new_session()

    def boom(step: SessionStep) -> None:
        raise RuntimeError("persistence layer broke")

    s._on_step = boom

    # Should not raise; step still appended.
    step = s.record_tool_use(
        agent_full_id="a@v1", tool_name="t", input_args={}
    )
    assert step is not None
    assert len(s.steps) == 1


def test_on_end_callback_fires_once() -> None:
    s = _new_session()
    fired: list[bool] = []
    s._on_end = lambda: fired.append(True)

    s.end_session()
    s.end_session()  # idempotente — nao deve refirear

    assert fired == [True]


# ─── Scratchpad ───────────────────────────────────────────────────────────


def test_scratchpad_render_empty_is_empty_string() -> None:
    pad = Scratchpad()
    assert pad.is_empty()
    assert pad.render() == ""


def test_scratchpad_append_and_render_cross_agent() -> None:
    pad = Scratchpad()

    pad.append(agent_name="sanity", text="Saldo consistente em 13/04.")
    pad.append(agent_name="decomposicao", text="Apropriacao DC explica 60%.")

    rendered = pad.render()
    assert "[Observacoes de agentes anteriores nesta analise]" in rendered
    assert "(sanity) Saldo consistente em 13/04." in rendered
    assert "(decomposicao) Apropriacao DC explica 60%." in rendered


def test_scratchpad_skips_blank_text() -> None:
    pad = Scratchpad()

    pad.append(agent_name="a", text="")
    pad.append(agent_name="a", text="   ")
    pad.append(agent_name="a", text="\n\t ")

    assert pad.is_empty()
    assert pad.entry_count == 0


def test_scratchpad_lru_cap_drops_oldest() -> None:
    pad = Scratchpad(max_chars=50)

    pad.append(agent_name="a", text="A" * 30)  # 30 chars
    pad.append(agent_name="b", text="B" * 20)  # 50 total — ok
    pad.append(agent_name="c", text="C" * 10)  # 60 — drops oldest (30)

    rendered = pad.render()
    assert "AAA" not in rendered  # oldest gone
    assert "BBB" in rendered
    assert "CCC" in rendered
    assert pad.entry_count == 2


def test_scratchpad_preserves_latest_when_singleton_exceeds_cap() -> None:
    pad = Scratchpad(max_chars=10)

    pad.append(agent_name="a", text="X" * 100)  # alone, exceeds cap

    # We keep the singleton (it's the latest); cap is best-effort.
    assert pad.entry_count == 1
    assert "X" * 100 in pad.render()


# ─── StepCache ────────────────────────────────────────────────────────────


def test_step_cache_miss_returns_none_and_increments_counter() -> None:
    cache = StepCache()

    result = cache.get("tool_a", {"k": 1})

    assert result is None
    assert cache.miss_count == 1
    assert cache.hit_count == 0
    assert cache.size == 0


def test_step_cache_hit_after_put() -> None:
    cache = StepCache()

    cache.put("tool_a", {"k": 1}, "payload-1")
    result = cache.get("tool_a", {"k": 1})

    assert result == "payload-1"
    assert cache.hit_count == 1
    assert cache.miss_count == 0


def test_step_cache_key_independent_of_args_dict_order() -> None:
    cache = StepCache()

    cache.put("tool_a", {"a": 1, "b": 2}, "payload")
    result = cache.get("tool_a", {"b": 2, "a": 1})

    assert result == "payload"


def test_step_cache_different_tools_isolated() -> None:
    cache = StepCache()

    cache.put("tool_a", {"k": 1}, "for-a")
    cache.put("tool_b", {"k": 1}, "for-b")

    assert cache.get("tool_a", {"k": 1}) == "for-a"
    assert cache.get("tool_b", {"k": 1}) == "for-b"


def test_step_cache_different_args_isolated() -> None:
    cache = StepCache()

    cache.put("tool_a", {"k": 1}, "v1")
    cache.put("tool_a", {"k": 2}, "v2")

    assert cache.get("tool_a", {"k": 1}) == "v1"
    assert cache.get("tool_a", {"k": 2}) == "v2"


# ─── AgentTool cacheable flag ─────────────────────────────────────────────


def test_agent_tool_cacheable_default_false() -> None:
    tool = AgentTool(
        name="x",
        description="d",
        input_schema={"type": "object"},
        handler=_dummy_handler,  # type: ignore[arg-type]
        module=Module.CREDITO,
        min_permission=Permission.READ,
    )
    assert tool.cacheable is False


def test_register_tool_passes_cacheable_through() -> None:
    ToolRegistry.clear_for_testing()

    @register_tool(
        name="cacheable_dummy_test",
        description="d",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        module=Module.CREDITO,
        min_permission=Permission.READ,
        cacheable=True,
    )
    async def _h(scope, args):  # type: ignore[no-untyped-def]
        return "ok"

    tool = ToolRegistry.get("cacheable_dummy_test")
    assert tool is not None
    assert tool.cacheable is True


async def _dummy_handler(scope, args):  # type: ignore[no-untyped-def]
    return "ok"


# ─── Memory tools (remember / recall) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_tools_remember_recall_roundtrip() -> None:
    s = _new_session()
    tools = make_memory_tools(s)
    by_name = {t.name: t for t in tools}

    assert "remember" in by_name
    assert "recall" in by_name

    remember = by_name["remember"]
    recall = by_name["recall"]

    out = await remember.handler(  # type: ignore[arg-type]
        None, {"key": "score_a", "value": 412}
    )
    assert "412" in out
    assert s.kv_store["score_a"] == 412

    out2 = await recall.handler(  # type: ignore[arg-type]
        None, {"key": "score_a"}
    )
    assert "412" in out2


@pytest.mark.asyncio
async def test_memory_tools_recall_missing_key_returns_marker() -> None:
    s = _new_session()
    tools = make_memory_tools(s)
    recall = next(t for t in tools if t.name == "recall")

    out = await recall.handler(None, {"key": "nope"})  # type: ignore[arg-type]
    assert "nada guardado" in out
    assert "nope" in out


@pytest.mark.asyncio
async def test_memory_tools_remember_rejects_empty_key() -> None:
    s = _new_session()
    tools = make_memory_tools(s)
    remember = next(t for t in tools if t.name == "remember")

    out = await remember.handler(None, {"key": "", "value": 1})  # type: ignore[arg-type]
    assert "Erro" in out
    assert s.kv_store == {}


@pytest.mark.asyncio
async def test_memory_tools_accept_object_value() -> None:
    s = _new_session()
    tools = make_memory_tools(s)
    remember = next(t for t in tools if t.name == "remember")
    recall = next(t for t in tools if t.name == "recall")

    payload = {"score": 412, "protests": 2, "tags": ["high_risk"]}
    await remember.handler(None, {"key": "cedente_a", "value": payload})  # type: ignore[arg-type]

    out = await recall.handler(None, {"key": "cedente_a"})  # type: ignore[arg-type]
    assert "412" in out
    assert "high_risk" in out
