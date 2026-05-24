"""Unit test — _render_context_for_prompt injects session scratchpad (C2 Task 6).

Garante que quando `ctx.session` tem scratchpad nao-vazio, o bloco
"[Observacoes de agentes anteriores nesta analise]" aparece no
user_text. Quando session ausente, o output e identico ao caminho
legado — backward compat preservado.
"""

from __future__ import annotations

import importlib.util
from uuid import uuid4

import pytest

from app.agentic.memory import create_session
from app.agentic.playbooks.nodes._base import NodeContext
from app.core.enums import Module

# runtime.py importa anthropic — skip se ausente.
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("anthropic") is None,
    reason="anthropic SDK ausente",
)


def _ctx_legacy(session=None) -> NodeContext:
    return NodeContext(
        run_id=uuid4(),
        tenant_id=uuid4(),
        node_id="n1",
        initiated_by=None,
        previous_outputs={
            "upstream_node": {
                "output": {"valor": 42, "descricao": "exemplo"},
                "duration_ms": 100,
            }
        },
        trigger_data={"dossier_id": "abc-123"},
        session=session,
    )


def test_render_includes_scratchpad_when_session_has_notes() -> None:
    from app.agentic.engine.runtime import _render_context_for_prompt

    session = create_session(
        tenant_id=uuid4(),
        started_by_user_id=uuid4(),
        module=Module.CREDITO,
        context_label="test:render",
    )
    session.scratchpad.append(
        agent_name="sanity_agent",
        text="Saldo consistente em 13/04, residuo R$ 0,00.",
    )
    session.scratchpad.append(
        agent_name="decomposicao_agent",
        text="Apropriacao DC explica 60% da variacao.",
    )

    ctx = _ctx_legacy(session=session)
    rendered = _render_context_for_prompt(ctx)

    assert "[Observacoes de agentes anteriores nesta analise]" in rendered
    assert "(sanity_agent) Saldo consistente em 13/04" in rendered
    assert "(decomposicao_agent) Apropriacao DC explica 60%" in rendered


def test_render_omits_scratchpad_block_when_session_is_none() -> None:
    from app.agentic.engine.runtime import _render_context_for_prompt

    ctx = _ctx_legacy(session=None)
    rendered = _render_context_for_prompt(ctx)

    assert "[Observacoes de agentes anteriores" not in rendered


def test_render_omits_scratchpad_block_when_session_empty() -> None:
    from app.agentic.engine.runtime import _render_context_for_prompt

    session = create_session(
        tenant_id=uuid4(),
        started_by_user_id=uuid4(),
        module=Module.CREDITO,
        context_label="test:empty",
    )
    ctx = _ctx_legacy(session=session)
    rendered = _render_context_for_prompt(ctx)

    assert "[Observacoes de agentes anteriores" not in rendered
