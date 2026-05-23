"""Memoria agentica — bloco 'session' das 3 camadas (CLAUDE.md sec 19.11).

Tres camadas:
    session   curto prazo, durante 1 analise (esta camada)
    tenant    medio prazo, preferencias + padroes (futuro)
    global    longo prazo, anonimizada (deferido, parecer juridico)

Granularidade da session: por ANALISE, nao por invocacao de agente. Uma
analise (dossie, conversa, run de workflow) cria 1 session que sobrevive
N invocacoes de agente sequenciais. Permite cross-agent memory.

Persistencia hibrida:
    in-process por default; background flush em DB quando > 60s OU
    end_session(). Sempre persiste se for chat multi-turn.

Isolamento (regra dura):
    tenant_id em TODA leitura de session/step. Vazamento entre tenants
    e falha critica de compliance (CLAUDE.md sec 10).

API publica:
    create_session(tenant_id, started_by_user_id, module, context_label)
    session.record_tool_use / record_tool_result / record_error / record_observation
    session.scratchpad.append / render
    session.step_cache.get / put
    session.steps_for_agent
    session.end_session
"""

from app.agentic.memory._base import (
    AnalysisSession,
    SessionStep,
    StepKind,
    create_session,
)
from app.agentic.memory.persistence import (
    attach_persistence,
    wait_for_pending_flushes,
)

__all__ = [
    "AnalysisSession",
    "SessionStep",
    "StepKind",
    "attach_persistence",
    "create_session",
    "wait_for_pending_flushes",
]
