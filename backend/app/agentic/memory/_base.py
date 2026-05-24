"""AnalysisSession + SessionStep + StepKind — primitivos da memoria de sessao.

Ver app/agentic/memory/__init__.py para a visao geral. Este modulo define:

    StepKind         enum com tipos de step que viram registrados
    SessionStep      dataclass append-only de UM step
    AnalysisSession  agregador in-memory de N steps de uma analise
    create_session   factory publica
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from app.agentic.memory.scratchpad import Scratchpad
    from app.agentic.memory.step_cache import StepCache
    from app.core.enums import Module

logger = logging.getLogger(__name__)


class StepKind(StrEnum):
    """Tipo do step registrado em AnalysisSession.

    Valores string-coerced — viram coluna text em agent_session_step (C3).
    """

    TOOL_USE = "tool_use"                 # agente chamou ferramenta
    TOOL_RESULT = "tool_result"           # ferramenta retornou
    SCRATCHPAD_WRITE = "scratchpad"       # agente escreveu observacao
    OBSERVATION = "observation"           # marcador livre (inicio/fim de agente)
    ERROR = "error"                       # tool/agent levantou excecao


@dataclass(slots=True)
class SessionStep:
    """Um step registrado em AnalysisSession (append-only).

    Construido pelos `record_*` da AnalysisSession; nunca mutado depois.
    Persistence layer (C3) copia direto para `agent_session_step` em DB.

    Shape compativel com `AgentToolLogEntry` do frontend
    (frontend/src/design-system/components/AgentLiveStatus/index.tsx):
    `iso_at`, `kind`, `tool_name`, `duration_ms`, `message`.
    """

    iso_at: datetime
    kind: StepKind
    step_index: int                                      # monotonic dentro da session
    agent_full_id: str | None = None                     # ex.: 'credito.financial_analyst@v1'
    tool_name: str | None = None
    duration_ms: int | None = None
    input_json: dict[str, Any] | None = None
    output_json: dict[str, Any] | None = None
    message: str | None = None                           # resumo human-readable
    error: str | None = None                             # so quando kind == ERROR

    def to_log_entry(self) -> dict[str, Any]:
        """Serializa no shape AgentToolLogEntry esperado pelo frontend.

        Campos: iso_at (ISO string), kind, tool_name, duration_ms, message.
        Outros campos (input/output_json, error) ficam no DB persistente
        mas nao sao expostos no log de UI (poluiria a timeline).
        """
        return {
            "iso_at": self.iso_at.isoformat(),
            "kind": self.kind.value,
            "tool_name": self.tool_name,
            "duration_ms": self.duration_ms,
            "message": self.message,
        }


@dataclass(slots=True)
class AnalysisSession:
    """Memoria de uma analise agentica (N invocacoes de agente sequenciais).

    Lifecycle:
        1. caller cria via `create_session(...)`
        2. passa pra `run_specialist_agent(session=...)` ate N vezes
        3. cada invocacao registra steps; scratchpad/cache acumulam
        4. `end_session()` finaliza + dispara flush (quando persistence
           layer C3 estiver attach)

    Isolamento:
        `tenant_id` e `module` sao IMUTAVEIS. Para outra empresa/tenant,
        crie outra session.

    Callbacks (`_on_step`, `_on_end`):
        Persistence layer (C3) anexa via `attach_persistence(session, ...)`.
        Default None — session puramente in-memory.
    """

    id: UUID
    tenant_id: UUID
    started_by_user_id: UUID | None
    module: Module
    started_at: datetime
    context_label: str                                   # 'dossier:abc-123', 'chat:conv-456', 'workflow:credito.dossie:run-X'

    scratchpad: Scratchpad
    step_cache: StepCache

    steps: list[SessionStep] = field(default_factory=list)
    # Structured key-value store backing the optional `remember`/`recall`
    # tools (memory/tools.py). Distinct from the textual `scratchpad`:
    # scratchpad is auto-injected into prompts; kv_store is opt-in via
    # tools when the agent needs to round-trip a structured value.
    kv_store: dict[str, Any] = field(default_factory=dict)
    ended_at: datetime | None = None
    _step_counter: int = 0

    _on_step: Callable[[SessionStep], None] | None = field(default=None, repr=False)
    _on_end: Callable[[], None] | None = field(default=None, repr=False)

    # ─── Step recording ───────────────────────────────────────────────────

    def _next_step_index(self) -> int:
        idx = self._step_counter
        self._step_counter += 1
        return idx

    def _emit(self, step: SessionStep) -> SessionStep:
        self.steps.append(step)
        if self._on_step is not None:
            try:
                self._on_step(step)
            except Exception:
                # Persistence callback nao pode quebrar runtime agentico.
                logger.exception("AnalysisSession._on_step callback raised")
        return step

    def record_tool_use(
        self,
        *,
        agent_full_id: str,
        tool_name: str,
        input_args: dict[str, Any],
    ) -> SessionStep:
        return self._emit(
            SessionStep(
                iso_at=datetime.now(UTC),
                kind=StepKind.TOOL_USE,
                step_index=self._next_step_index(),
                agent_full_id=agent_full_id,
                tool_name=tool_name,
                input_json=dict(input_args),
                message=f"-> {tool_name}",
            )
        )

    def record_tool_result(
        self,
        *,
        agent_full_id: str,
        tool_name: str,
        output: str,
        duration_ms: int,
        from_cache: bool = False,
    ) -> SessionStep:
        suffix = " [cache]" if from_cache else ""
        # Cap output em 4000 chars dentro do step (DB-friendly). Output
        # bruto continua disponivel via runtime — este e so trace.
        return self._emit(
            SessionStep(
                iso_at=datetime.now(UTC),
                kind=StepKind.TOOL_RESULT,
                step_index=self._next_step_index(),
                agent_full_id=agent_full_id,
                tool_name=tool_name,
                duration_ms=duration_ms,
                output_json={"text": output[:4000]},
                message=f"<- {tool_name} ({duration_ms}ms){suffix}",
            )
        )

    def record_error(
        self,
        *,
        agent_full_id: str | None,
        tool_name: str | None,
        error: str,
    ) -> SessionStep:
        label = tool_name or agent_full_id or "session"
        return self._emit(
            SessionStep(
                iso_at=datetime.now(UTC),
                kind=StepKind.ERROR,
                step_index=self._next_step_index(),
                agent_full_id=agent_full_id,
                tool_name=tool_name,
                error=error,
                message=f"erro em {label}: {error[:200]}",
            )
        )

    def record_observation(
        self,
        *,
        agent_full_id: str | None,
        message: str,
    ) -> SessionStep:
        return self._emit(
            SessionStep(
                iso_at=datetime.now(UTC),
                kind=StepKind.OBSERVATION,
                step_index=self._next_step_index(),
                agent_full_id=agent_full_id,
                message=message,
            )
        )

    def record_scratchpad_write(
        self,
        *,
        agent_full_id: str,
        text: str,
    ) -> SessionStep:
        """Marca no trace que o scratchpad foi escrito.

        Conteudo bruto fica em `self.scratchpad`; este step e so trace.
        """
        return self._emit(
            SessionStep(
                iso_at=datetime.now(UTC),
                kind=StepKind.SCRATCHPAD_WRITE,
                step_index=self._next_step_index(),
                agent_full_id=agent_full_id,
                message=text[:200],
                output_json={"text": text[:4000]},
            )
        )

    # ─── Queries ──────────────────────────────────────────────────────────

    def steps_for_agent(self, agent_full_id: str) -> list[SessionStep]:
        """Steps que pertencem a uma invocacao de agente especifica.

        Usado pelo engine de workflow para popular
        `PlaybookRunStep.input_data['tools_log']` (C2/Task 7).
        """
        return [s for s in self.steps if s.agent_full_id == agent_full_id]

    @property
    def duration_seconds(self) -> float:
        """Tempo decorrido em segundos (continua contando ate end_session)."""
        end = self.ended_at or datetime.now(UTC)
        return (end - self.started_at).total_seconds()

    @property
    def step_count(self) -> int:
        return len(self.steps)

    # ─── Lifecycle ────────────────────────────────────────────────────────

    def end_session(self) -> None:
        """Finaliza a session.

        Idempotente — chamadas repetidas sao no-op. Dispara `_on_end`
        callback (persistence layer faz flush sincrono aqui em C3).
        """
        if self.ended_at is not None:
            return
        self.ended_at = datetime.now(UTC)
        if self._on_end is not None:
            try:
                self._on_end()
            except Exception:
                logger.exception("AnalysisSession._on_end callback raised")


def create_session(
    *,
    tenant_id: UUID,
    started_by_user_id: UUID | None,
    module: Module,
    context_label: str,
) -> AnalysisSession:
    """Factory de AnalysisSession in-memory.

    `tenant_id` obrigatorio — isolamento e regra dura (CLAUDE.md sec 10).
    `context_label` ajuda a rastrear o que essa session esta cobrindo
    (ex.: 'dossier:abc-123', 'workflow:credito.dossie:run-456').

    Persistencia (DB write) e anexada por `app.agentic.memory.persistence`
    em C3 — este factory cria apenas a session in-memory.
    """
    # Lazy import: evita circular ao mesmo tempo que mantem o factory aqui.
    from app.agentic.memory.scratchpad import Scratchpad
    from app.agentic.memory.step_cache import StepCache

    return AnalysisSession(
        id=uuid4(),
        tenant_id=tenant_id,
        started_by_user_id=started_by_user_id,
        module=module,
        started_at=datetime.now(UTC),
        context_label=context_label,
        scratchpad=Scratchpad(),
        step_cache=StepCache(),
    )
