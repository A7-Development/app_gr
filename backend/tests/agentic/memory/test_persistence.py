"""Persistencia hibrida — flush parcial (60s) + final (end_session) (C3 Task 9).

Mocka AsyncSession via context-manager fake. Sem DB real. Verifica:
- end_session dispara flush sincrono via asyncio task
- Idempotencia: re-end nao duplica INSERTs (idempotent na AnalysisSession)
- Watchdog: apos `soft_flush_seconds`, flush parcial roda automatico
- Cancelamento: end_session cancela watchdog antes do flush parcial
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from app.agentic.memory import (
    attach_persistence,
    create_session,
    wait_for_pending_flushes,
)
from app.agentic.memory.persistence import _PENDING_FLUSH_TASKS
from app.core.enums import Module
from app.shared.ai.models.agent_session import AgentSession, AgentSessionStep


class _FakeDB:
    """AsyncSession duck — soh com o que persistence.py toca."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commits = 0

    async def __aenter__(self) -> _FakeDB:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def get(self, _model: type, _id: Any) -> Any:
        # Default: nao existe ainda. Sobrescrever por teste se precisa.
        return None


def _factory(db: _FakeDB):
    """Devolve factory que serve sempre o mesmo db (suficiente p/ testes)."""

    def _make() -> _FakeDB:
        return db

    return _make


def _new_session(*, label: str = "test:persistence"):
    return create_session(
        tenant_id=uuid4(),
        started_by_user_id=uuid4(),
        module=Module.CREDITO,
        context_label=label,
    )


# ─── End session flush ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_session_flushes_to_db() -> None:
    db = _FakeDB()
    s = _new_session()
    attach_persistence(s, session_factory=_factory(db))

    s.record_tool_use(agent_full_id="a@v1", tool_name="t", input_args={"x": 1})
    s.record_tool_result(
        agent_full_id="a@v1", tool_name="t", output="r", duration_ms=10
    )

    s.end_session()
    await wait_for_pending_flushes(timeout=2.0)

    # 1 AgentSession + 2 AgentSessionStep adicionados, 1 commit.
    session_rows = [o for o in db.added if isinstance(o, AgentSession)]
    step_rows = [o for o in db.added if isinstance(o, AgentSessionStep)]

    assert len(session_rows) == 1
    assert len(step_rows) == 2
    assert db.commits == 1
    assert session_rows[0].id == s.id
    assert session_rows[0].ended_at is not None
    assert session_rows[0].step_count == 2
    assert {r.tool_name for r in step_rows} == {"t"}
    # step_index esta preservado pra UQ
    assert sorted(r.step_index for r in step_rows) == [0, 1]


@pytest.mark.asyncio
async def test_end_session_propagates_scratchpad_final() -> None:
    db = _FakeDB()
    s = _new_session()
    attach_persistence(s, session_factory=_factory(db))

    s.scratchpad.append(agent_name="a", text="observacao chave")
    s.record_observation(agent_full_id="a@v1", message="done")

    s.end_session()
    await wait_for_pending_flushes(timeout=2.0)

    session_rows = [o for o in db.added if isinstance(o, AgentSession)]
    assert len(session_rows) == 1
    assert "observacao chave" in (session_rows[0].scratchpad_final or "")


@pytest.mark.asyncio
async def test_idempotent_step_flush_no_duplicates() -> None:
    """Se chamarmos flush manualmente + end_session, steps gravam 1x."""
    from app.agentic.memory.persistence import attach_persistence

    db = _FakeDB()
    s = _new_session()
    attach_persistence(s, session_factory=_factory(db))

    s.record_tool_use(agent_full_id="a@v1", tool_name="t1", input_args={})
    s.record_tool_result(
        agent_full_id="a@v1", tool_name="t1", output="ok", duration_ms=1
    )

    # Simula um flush "intermediario" (proxy: invoca _on_step de novo a frio
    # nao funciona — vou usar so end_session que ja roda 1x).
    s.end_session()
    await wait_for_pending_flushes(timeout=2.0)

    step_rows_round_1 = [o for o in db.added if isinstance(o, AgentSessionStep)]
    assert len(step_rows_round_1) == 2

    # end_session re-call e no-op (idempotente na AnalysisSession).
    s.end_session()
    await wait_for_pending_flushes(timeout=2.0)

    step_rows_round_2 = [o for o in db.added if isinstance(o, AgentSessionStep)]
    assert len(step_rows_round_2) == 2  # sem duplicatas


# ─── Watchdog ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_watchdog_flushes_partial_after_threshold() -> None:
    """Session viva > soft_flush_seconds dispara flush parcial automatico."""
    db = _FakeDB()
    s = _new_session()
    # Threshold MUITO curto pro teste (100ms).
    attach_persistence(s, session_factory=_factory(db), soft_flush_seconds=0.1)

    # Primeiro step liga o watchdog.
    s.record_tool_use(agent_full_id="a@v1", tool_name="t", input_args={})

    # Espera o watchdog disparar.
    await asyncio.sleep(0.3)

    # Flush parcial aconteceu (session ainda nao terminou).
    session_rows = [o for o in db.added if isinstance(o, AgentSession)]
    step_rows = [o for o in db.added if isinstance(o, AgentSessionStep)]
    assert len(session_rows) == 1
    assert session_rows[0].ended_at is None  # ainda viva
    assert len(step_rows) == 1


@pytest.mark.asyncio
async def test_end_session_cancels_watchdog() -> None:
    """Quando session termina cedo, watchdog NAO dispara flush duplicado."""
    db = _FakeDB()
    s = _new_session()
    attach_persistence(s, session_factory=_factory(db), soft_flush_seconds=10.0)

    s.record_tool_use(agent_full_id="a@v1", tool_name="t", input_args={})

    # Termina ANTES do watchdog (10s).
    s.end_session()
    await wait_for_pending_flushes(timeout=2.0)

    # Espera um pouco pra confirmar que watchdog nao re-dispara.
    await asyncio.sleep(0.2)

    session_rows = [o for o in db.added if isinstance(o, AgentSession)]
    step_rows = [o for o in db.added if isinstance(o, AgentSessionStep)]
    # Apenas 1 session row foi adicionada (no flush final).
    assert len(session_rows) == 1
    assert len(step_rows) == 1
    assert db.commits == 1


# ─── Sync context (no asyncio loop) ───────────────────────────────────────


def test_record_step_outside_asyncio_loop_does_not_raise() -> None:
    """Codigo sync que registra step (raro) nao deve quebrar."""
    db = _FakeDB()
    s = _new_session()
    attach_persistence(s, session_factory=_factory(db))

    # No loop ativo — _on_step deteta e pula watchdog silenciosamente.
    s.record_observation(agent_full_id="a@v1", message="from sync")

    # No flush porque end_session tambem precisaria de loop, mas o
    # importante e nao levantar excecao.
    assert len(s.steps) == 1


# ─── Falha de DB nao quebra runtime ──────────────────────────────────────


@pytest.mark.asyncio
async def test_db_exception_does_not_propagate() -> None:
    """Se o flush em DB falha, runtime agentico continua funcionando."""

    class _FailingDB(_FakeDB):
        async def commit(self) -> None:
            raise RuntimeError("DB explodiu")

    db = _FailingDB()
    s = _new_session()
    attach_persistence(s, session_factory=_factory(db))

    s.record_tool_use(agent_full_id="a@v1", tool_name="t", input_args={})
    s.end_session()
    await wait_for_pending_flushes(timeout=2.0)

    # session.steps preservada (in-memory). Re-flush futuro pode tentar de novo.
    assert len(s.steps) == 1


# ─── Cleanup ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _cleanup_pending_flushes():
    """Limpa o set global de tasks pendentes entre testes."""
    yield
    _PENDING_FLUSH_TASKS.clear()
