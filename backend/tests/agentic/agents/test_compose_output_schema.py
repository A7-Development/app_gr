"""Tests for auto-injection of the output_schema into the system prompt.

Run isolated (pure):
    pytest backend/tests/agentic/agents/test_compose_output_schema.py --noconftest
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.agentic.agents._compose import (
    compose_system_text,
    render_output_schema_block,
)


class _Sample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str
    nivel: str


def test_block_contains_field_names_and_directives():
    blk = render_output_schema_block(_Sample)
    assert blk is not None
    assert "<output_format>" in blk and "</output_format>" in blk
    assert "titulo" in blk and "nivel" in blk
    # diretiva de nomes exatos + caminho sem-dados
    assert "EXATAMENTE" in blk
    assert "campos obrigatorios" in blk


def test_none_for_non_schema():
    assert render_output_schema_block(None) is None
    assert render_output_schema_block("nao e um modelo") is None


def test_compose_appends_after_task():
    out = compose_system_text(
        persona=None,
        expertises=[],
        prompt_system_text="MINHA TAREFA",
        output_schema=_Sample,
    )
    assert "<task>" in out and "MINHA TAREFA" in out
    # output_format vem DEPOIS da task
    assert out.index("<task>") < out.index("<output_format>")


def test_compose_without_schema_is_backcompat():
    out = compose_system_text(
        persona=None, expertises=[], prompt_system_text="X"
    )
    assert "<output_format>" not in out
    assert "<task>" in out
