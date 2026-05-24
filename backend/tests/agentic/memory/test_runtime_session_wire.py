"""Wire test — _run_tool_loop instrumenta a AnalysisSession (C2 Task 5).

Fake `AsyncAnthropic` client devolve uma sequencia pre-determinada de
respostas (tool_use -> tool_result -> end_turn). Verifica que cada
tool call e registrada em `session.steps`, que tools `cacheable=True`
acertam o `step_cache` na segunda chamada com mesmos args, e que
erros do handler viram step_error sem quebrar o loop.

NAO importa runtime.py se anthropic nao estiver instalado — usa
importlib.util pra checar primeiro.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from app.agentic._scope import ScopedContext
from app.agentic.memory import StepKind, create_session
from app.agentic.tools._base import AgentTool
from app.core.enums import Module, Permission

# Skip do modulo inteiro se anthropic SDK nao esta instalado (ambiente
# minimo). O runtime real precisa dele; em CI/prod sempre tem.
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("anthropic") is None,
    reason="anthropic SDK ausente neste ambiente",
)


# ─── Fakes ────────────────────────────────────────────────────────────────


@dataclass
class _FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 50
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


@dataclass
class _FakeResponse:
    stop_reason: str
    content: list[Any]
    usage: _FakeUsage

    def __post_init__(self) -> None:
        # Patch model_dump pros blocks (o runtime serializa pra mensagem).
        for block in self.content:
            if not hasattr(block, "model_dump"):
                d = dict(block.__dict__)
                block.model_dump = lambda d=d: d  # type: ignore[attr-defined]


class _FakeMessages:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._queue = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        if not self._queue:
            raise RuntimeError("Fake exhausted — test setup error")
        return self._queue.pop(0)


class _FakeClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.messages = _FakeMessages(responses)


# ─── Helpers ──────────────────────────────────────────────────────────────


def _make_scope(db: Any = None) -> ScopedContext:
    return ScopedContext(
        tenant_id=uuid4(),
        empresa_id=None,
        user_id=uuid4(),
        module=Module.CREDITO,
        permissions={Module.CREDITO: Permission.READ},
        db=db,  # type: ignore[arg-type]
        extras={},
    )


def _make_tool(
    name: str,
    handler: Any,
    *,
    cacheable: bool = False,
) -> AgentTool:
    return AgentTool(
        name=name,
        description=f"test tool {name}",
        input_schema={"type": "object", "additionalProperties": True},
        handler=handler,
        module=Module.CREDITO,
        min_permission=Permission.READ,
        cacheable=cacheable,
    )


def _make_spec(name: str = "test_agent") -> Any:
    # Minimal duck — _run_tool_loop usa apenas `name` e `thinking_budget_tokens`.
    @dataclass
    class _Spec:
        name: str
        thinking_budget_tokens: int = 1000

    return _Spec(name=name)


# ─── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_use_and_result_get_recorded_on_session() -> None:
    from app.agentic.engine.runtime import _run_tool_loop

    session = create_session(
        tenant_id=uuid4(),
        started_by_user_id=uuid4(),
        module=Module.CREDITO,
        context_label="test:session",
    )

    call_count = {"n": 0}

    async def echo_handler(scope: ScopedContext, args: dict[str, Any]) -> str:
        call_count["n"] += 1
        return f"echo:{args.get('x', '?')}"

    tool = _make_tool("echo", echo_handler)

    fake_client = _FakeClient(
        [
            _FakeResponse(
                stop_reason="tool_use",
                content=[
                    _FakeToolUseBlock(id="tu1", name="echo", input={"x": 1}),
                ],
                usage=_FakeUsage(),
            ),
            _FakeResponse(
                stop_reason="end_turn",
                content=[_FakeTextBlock(text="final answer")],
                usage=_FakeUsage(),
            ),
        ]
    )

    text, _usage = await _run_tool_loop(
        client=fake_client,  # type: ignore[arg-type]
        spec=_make_spec(),
        model="model-x",
        fallback_model=None,
        system_text="system",
        user_text="user",
        tools=[tool],
        scope=_make_scope(),
        session=session,
        agent_full_id="test.agent@v1",
    )

    assert text == "final answer"
    assert call_count["n"] == 1

    kinds = [s.kind for s in session.steps]
    assert StepKind.TOOL_USE in kinds
    assert StepKind.TOOL_RESULT in kinds

    use_step = next(s for s in session.steps if s.kind == StepKind.TOOL_USE)
    assert use_step.tool_name == "echo"
    assert use_step.input_json == {"x": 1}
    assert use_step.agent_full_id == "test.agent@v1"

    res_step = next(s for s in session.steps if s.kind == StepKind.TOOL_RESULT)
    assert res_step.tool_name == "echo"
    assert res_step.duration_ms is not None
    assert res_step.duration_ms >= 0
    assert res_step.output_json is not None
    assert "echo:1" in res_step.output_json["text"]


@pytest.mark.asyncio
async def test_cacheable_tool_hits_cache_on_second_call_with_same_args() -> None:
    from app.agentic.engine.runtime import _run_tool_loop

    session = create_session(
        tenant_id=uuid4(),
        started_by_user_id=uuid4(),
        module=Module.CREDITO,
        context_label="test:cache",
    )

    call_count = {"n": 0}

    async def expensive_handler(
        scope: ScopedContext, args: dict[str, Any]
    ) -> str:
        call_count["n"] += 1
        return f"computed_{call_count['n']}"

    tool = _make_tool("expensive", expensive_handler, cacheable=True)

    fake_client = _FakeClient(
        [
            _FakeResponse(
                stop_reason="tool_use",
                content=[
                    _FakeToolUseBlock(id="tu1", name="expensive", input={"k": 1}),
                ],
                usage=_FakeUsage(),
            ),
            _FakeResponse(
                stop_reason="tool_use",
                content=[
                    _FakeToolUseBlock(id="tu2", name="expensive", input={"k": 1}),
                ],
                usage=_FakeUsage(),
            ),
            _FakeResponse(
                stop_reason="end_turn",
                content=[_FakeTextBlock(text="done")],
                usage=_FakeUsage(),
            ),
        ]
    )

    await _run_tool_loop(
        client=fake_client,  # type: ignore[arg-type]
        spec=_make_spec(),
        model="model-x",
        fallback_model=None,
        system_text="system",
        user_text="user",
        tools=[tool],
        scope=_make_scope(),
        session=session,
        agent_full_id="test.agent@v1",
    )

    # Handler chamado UMA vez (segunda foi cache hit).
    assert call_count["n"] == 1

    # Step cache marca hit.
    assert session.step_cache.hit_count == 1

    # Segundo TOOL_RESULT veio do cache — message tem '[cache]'.
    result_steps = [s for s in session.steps if s.kind == StepKind.TOOL_RESULT]
    assert len(result_steps) == 2
    assert result_steps[0].message is not None and "[cache]" not in result_steps[0].message
    assert result_steps[1].message is not None and "[cache]" in result_steps[1].message
    # Output e identico (mesmo valor cacheado).
    assert result_steps[0].output_json == result_steps[1].output_json


@pytest.mark.asyncio
async def test_non_cacheable_tool_re_executes_handler() -> None:
    from app.agentic.engine.runtime import _run_tool_loop

    session = create_session(
        tenant_id=uuid4(),
        started_by_user_id=uuid4(),
        module=Module.CREDITO,
        context_label="test:nocache",
    )

    call_count = {"n": 0}

    async def stateful_handler(
        scope: ScopedContext, args: dict[str, Any]
    ) -> str:
        call_count["n"] += 1
        return f"call_{call_count['n']}"

    tool = _make_tool("stateful", stateful_handler, cacheable=False)

    fake_client = _FakeClient(
        [
            _FakeResponse(
                stop_reason="tool_use",
                content=[
                    _FakeToolUseBlock(id="t1", name="stateful", input={"k": 1}),
                ],
                usage=_FakeUsage(),
            ),
            _FakeResponse(
                stop_reason="tool_use",
                content=[
                    _FakeToolUseBlock(id="t2", name="stateful", input={"k": 1}),
                ],
                usage=_FakeUsage(),
            ),
            _FakeResponse(
                stop_reason="end_turn",
                content=[_FakeTextBlock(text="done")],
                usage=_FakeUsage(),
            ),
        ]
    )

    await _run_tool_loop(
        client=fake_client,  # type: ignore[arg-type]
        spec=_make_spec(),
        model="model-x",
        fallback_model=None,
        system_text="system",
        user_text="user",
        tools=[tool],
        scope=_make_scope(),
        session=session,
        agent_full_id="test.agent@v1",
    )

    # Sem cache: handler invocado nas DUAS vezes.
    assert call_count["n"] == 2
    assert session.step_cache.hit_count == 0


@pytest.mark.asyncio
async def test_handler_exception_records_error_step_and_continues() -> None:
    from app.agentic.engine.runtime import _run_tool_loop

    session = create_session(
        tenant_id=uuid4(),
        started_by_user_id=uuid4(),
        module=Module.CREDITO,
        context_label="test:error",
    )

    async def boom_handler(scope: ScopedContext, args: dict[str, Any]) -> str:
        raise RuntimeError("tool exploded")

    tool = _make_tool("boom", boom_handler)

    fake_client = _FakeClient(
        [
            _FakeResponse(
                stop_reason="tool_use",
                content=[
                    _FakeToolUseBlock(id="t1", name="boom", input={}),
                ],
                usage=_FakeUsage(),
            ),
            _FakeResponse(
                stop_reason="end_turn",
                content=[_FakeTextBlock(text="recovered")],
                usage=_FakeUsage(),
            ),
        ]
    )

    text, _usage = await _run_tool_loop(
        client=fake_client,  # type: ignore[arg-type]
        spec=_make_spec(),
        model="model-x",
        fallback_model=None,
        system_text="system",
        user_text="user",
        tools=[tool],
        scope=_make_scope(),
        session=session,
        agent_full_id="test.agent@v1",
    )

    assert text == "recovered"

    error_steps = [s for s in session.steps if s.kind == StepKind.ERROR]
    assert len(error_steps) == 1
    assert error_steps[0].tool_name == "boom"
    assert "tool exploded" in (error_steps[0].error or "")


@pytest.mark.asyncio
async def test_session_none_does_not_break_loop() -> None:
    """Backward compat: codigo legado chama sem session — nao quebra."""
    from app.agentic.engine.runtime import _run_tool_loop

    async def h(scope: ScopedContext, args: dict[str, Any]) -> str:
        return "ok"

    tool = _make_tool("t", h)

    fake_client = _FakeClient(
        [
            _FakeResponse(
                stop_reason="tool_use",
                content=[_FakeToolUseBlock(id="x", name="t", input={})],
                usage=_FakeUsage(),
            ),
            _FakeResponse(
                stop_reason="end_turn",
                content=[_FakeTextBlock(text="bye")],
                usage=_FakeUsage(),
            ),
        ]
    )

    text, _usage = await _run_tool_loop(
        client=fake_client,  # type: ignore[arg-type]
        spec=_make_spec(),
        model="model-x",
        fallback_model=None,
        system_text="system",
        user_text="user",
        tools=[tool],
        scope=_make_scope(),
        session=None,  # explicit no-session
    )

    assert text == "bye"
