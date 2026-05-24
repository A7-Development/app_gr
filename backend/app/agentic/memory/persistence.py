"""Persistencia hibrida da AnalysisSession (CLAUDE.md sec 19.11).

Estrategia:
    1. Steps NAO vao a DB a cada record_* — ficam in-memory.
    2. Watchdog dispara `_DEFAULT_SOFT_FLUSH_SECONDS` apos o primeiro
       step. Se a session ainda nao terminou, faz flush parcial dos
       steps acumulados. Cobre sessions longas que poderiam ser
       perdidas em caso de restart.
    3. end_session() faz flush final (idempotente — re-chamadas no-op).

Quando aplicar:
    `attach_persistence(session, async_session_maker)` apos
    `create_session(...)`. async_session_maker e um callable que
    devolve um AsyncSession context manager (ex.: `AsyncSessionLocal`).

Por que NAO usar a AsyncSession da request:
    A AsyncSession do caller (workflow engine, endpoint) tipicamente
    e fechada quando o request termina. Flush em background acontece
    DEPOIS — precisa de session propria, isolada.

Idempotencia:
    `flushed_step_indices` rastreia steps ja persistidos. Watchdog
    + end_session() podem coexistir; nao duplicam INSERTs.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from app.agentic.memory._base import AnalysisSession, SessionStep
from app.shared.ai.models.agent_session import AgentSession, AgentSessionStep

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Apos N segundos vivos, dispara flush parcial dos steps acumulados.
# Default 60s — equilibra "perda em caso de crash" com "carga em DB pra
# sessoes longas". Override por session via param em attach_persistence.
_DEFAULT_SOFT_FLUSH_SECONDS = 60.0


# Type alias: factory que devolve uma AsyncSession context manager.
# Compativel com `AsyncSessionLocal` (do app.core.database).
SessionFactory = Callable[[], contextlib.AbstractAsyncContextManager["AsyncSession"]]


def attach_persistence(
    session: AnalysisSession,
    *,
    session_factory: SessionFactory,
    soft_flush_seconds: float = _DEFAULT_SOFT_FLUSH_SECONDS,
) -> None:
    """Anexa callbacks _on_step e _on_end pra persistir em DB hibridamente.

    Apos esta chamada:
    - O primeiro step dispara um watchdog assincrono que esperara
      `soft_flush_seconds` segundos. Se a session passa do limite sem
      end_session(), faz flush parcial.
    - end_session() dispara flush final sincrono (cancela watchdog +
      gera asyncio.Task pro flush). Re-chamadas de end_session sao
      no-op pela propria AnalysisSession.

    A funcao NAO bloqueia — toda I/O acontece em tasks de background.

    Args:
        session: AnalysisSession ja criada via `create_session(...)`.
        session_factory: callable sem args que devolve AsyncSession
            context manager. Em app real: `AsyncSessionLocal`.
        soft_flush_seconds: threshold do watchdog. Default 60s.
    """
    # State compartilhado entre callbacks via closure.
    flushed_step_indices: set[int] = set()
    flush_lock = asyncio.Lock()
    watchdog_handle: asyncio.Task[None] | None = None
    persistence_active = True  # disable cleanup quando flush ja rodou

    async def _flush_unflushed() -> None:
        """Flush incremental: persiste steps ainda nao gravados.

        Idempotente — usa `flushed_step_indices` pra nao duplicar.
        Insere agent_session row sob demanda (primeira call) e
        atualiza-a (subsequentes).
        """
        async with flush_lock:
            unflushed = [
                s for s in session.steps
                if s.step_index not in flushed_step_indices
            ]

            # Sempre atualiza agent_session row (mesmo sem steps novos —
            # ended_at e scratchpad_final podem ter mudado).
            try:
                async with session_factory() as db:
                    existing = await db.get(AgentSession, session.id)
                    if existing is None:
                        db.add(
                            AgentSession(
                                id=session.id,
                                tenant_id=session.tenant_id,
                                started_by_user_id=session.started_by_user_id,
                                module=session.module.value,
                                context_label=session.context_label,
                                started_at=session.started_at,
                                ended_at=session.ended_at,
                                scratchpad_final=(
                                    session.scratchpad.render() or None
                                    if session.ended_at is not None
                                    else None
                                ),
                                step_count=len(session.steps),
                            )
                        )
                    else:
                        existing.ended_at = session.ended_at
                        if session.ended_at is not None:
                            existing.scratchpad_final = (
                                session.scratchpad.render() or None
                            )
                        existing.step_count = len(session.steps)

                    # Steps novos
                    for step in unflushed:
                        db.add(
                            AgentSessionStep(
                                tenant_id=session.tenant_id,
                                session_id=session.id,
                                agent_full_id=step.agent_full_id,
                                step_index=step.step_index,
                                iso_at=step.iso_at,
                                kind=step.kind.value,
                                tool_name=step.tool_name,
                                duration_ms=step.duration_ms,
                                input_json=step.input_json,
                                output_json=step.output_json,
                                message=step.message,
                                error=step.error,
                            )
                        )
                        flushed_step_indices.add(step.step_index)

                    await db.commit()
            except Exception:
                logger.exception(
                    "AnalysisSession persistence flush falhou (session_id=%s)",
                    session.id,
                )
                # Persistence nao pode quebrar runtime agentico. Steps
                # ficam in-memory; proxima chamada tenta de novo.

    async def _watchdog() -> None:
        try:
            await asyncio.sleep(soft_flush_seconds)
            if session.ended_at is None and persistence_active:
                await _flush_unflushed()
        except asyncio.CancelledError:
            # Cancelado por end_session — esperado.
            pass

    def _on_step(_step: SessionStep) -> None:
        nonlocal watchdog_handle
        # Lazy-spawn watchdog ao primeiro step (sessions que nunca
        # registram step nao geram task de background).
        if watchdog_handle is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # Sem loop ativo (codigo sync) — sem persistencia.
                # Logamos uma vez pra nao poluir.
                logger.debug(
                    "AnalysisSession step recorded outside asyncio loop; "
                    "persistence watchdog nao iniciado"
                )
                return
            watchdog_handle = loop.create_task(_watchdog())

    def _on_end() -> None:
        nonlocal persistence_active
        persistence_active = False
        # Cancela watchdog se ainda rodando — vamos flushar agora.
        if watchdog_handle is not None and not watchdog_handle.done():
            watchdog_handle.cancel()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "end_session fora de asyncio loop (session_id=%s); "
                "persistencia pulada",
                session.id,
            )
            return
        # Fire-and-forget flush final. Mantem ref pra nao ser garbage-
        # collected antes de concluir.
        task = loop.create_task(_flush_unflushed())
        _PENDING_FLUSH_TASKS.add(task)
        task.add_done_callback(_PENDING_FLUSH_TASKS.discard)

    session._on_step = _on_step
    session._on_end = _on_end


# Conjunto de tasks de flush pendentes — referencia forte impede que
# o GC do asyncio derrube fire-and-forget no meio do INSERT. Removido
# pelo done callback quando completa.
_PENDING_FLUSH_TASKS: set[asyncio.Task[None]] = set()


async def wait_for_pending_flushes(timeout: float | None = None) -> None:
    """Espera todas as tasks de flush pendentes concluirem.

    Util em shutdown de processo (graceful drain) e em testes. Sem
    timeout = espera indefinidamente. Com timeout = retorna apos N
    segundos mesmo com tasks vivas.
    """
    if not _PENDING_FLUSH_TASKS:
        return
    # asyncio.wait copia o set — seguro contra mutacao concorrente.
    await asyncio.wait(_PENDING_FLUSH_TASKS, timeout=timeout)
