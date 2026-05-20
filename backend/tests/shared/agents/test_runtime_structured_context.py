"""Specialist agent runtime — structured input contract (Phase A).

Covers the migration from "previous_outputs as truncated text dump" to
"named structured JSON of declared input slots". Both paths must work:

- Structured path: when `spec.inputs` is non-empty AND the node config
  contains `input_bindings`, _render_context_for_prompt resolves each
  slot to a clean named dict and emits it as a single JSON block.

- Legacy path: when `spec.inputs` is empty OR no bindings exist, the
  function falls back to the existing behavior (full previous_outputs
  dump, truncated 2000 chars/node).

The SpecialistAgentNode.requires() also gets exercised: it must emit one
typed Requirement per declared slot, deriving from spec.inputs + the
node's input_bindings.
"""

from __future__ import annotations

from uuid import uuid4

from app.agentic.engine.catalog import CATALOG, AgentInput, SpecialistAgentSpec
from app.agentic.engine.output_schemas import FinancialAnalysis
from app.agentic.engine.runtime import _render_context_for_prompt
from app.shared.workflow.nodes._base import NodeContext, VarType
from app.shared.workflow.nodes.specialist_agent import SpecialistAgentNode


def _ctx(
    *,
    previous_outputs: dict | None = None,
    trigger_data: dict | None = None,
    node_config: dict | None = None,
) -> NodeContext:
    return NodeContext(
        run_id=uuid4(),
        tenant_id=uuid4(),
        node_id="financial_node",
        initiated_by=None,
        previous_outputs=previous_outputs or {},
        trigger_data=trigger_data or {},
        node_config=node_config or {},
    )


# ─── Structured path ──────────────────────────────────────────────────────


def test_structured_context_emits_named_json_with_resolved_refs() -> None:
    spec = SpecialistAgentSpec(
        name="test_agent",
        description="",
        prompt_name="agent.test",
        tools=(),
        output_schema=FinancialAnalysis,
        section_id="financial",
        inputs=(
            AgentInput(name="cnpj", type=VarType.CNPJ),
            AgentInput(name="score_pj", type=VarType.SCORE, optional=True),
            AgentInput(name="ebitda", type=VarType.MONEY_BRL, optional=True),
        ),
    )
    ctx = _ctx(
        trigger_data={"cnpj": "12345678000199"},
        previous_outputs={
            "bureau": {"output": {"score_pj": 720}},
            "ocr": {"output": {"extracted_data": {"ebitda": 1_800_000}}},
        },
    )
    bindings = {
        "cnpj": "trigger.cnpj",
        "score_pj": "node.bureau.output.score_pj",
        "ebitda": "node.ocr.output.extracted_data.ebitda",
    }
    text = _render_context_for_prompt(
        ctx, spec=spec, config={"input_bindings": bindings}
    )
    assert "[Dados disponiveis para sua analise]" in text
    # Bloco JSON contem cada slot resolvido pelo nome.
    assert '"cnpj": "12345678000199"' in text
    assert '"score_pj": 720' in text
    assert '"ebitda": 1800000' in text
    # NAO contem o dump legacy.
    assert "[Outputs de nos anteriores]" not in text


def test_structured_context_unbound_optional_resolves_to_null() -> None:
    spec = SpecialistAgentSpec(
        name="test_agent",
        description="",
        prompt_name="agent.test",
        tools=(),
        output_schema=FinancialAnalysis,
        section_id="financial",
        inputs=(
            AgentInput(name="cnpj", type=VarType.CNPJ),
            AgentInput(name="score_pj", type=VarType.SCORE, optional=True),
        ),
    )
    ctx = _ctx(trigger_data={"cnpj": "12345678000199"})
    text = _render_context_for_prompt(
        ctx, spec=spec, config={"input_bindings": {"cnpj": "trigger.cnpj"}}
    )
    assert '"cnpj": "12345678000199"' in text
    assert '"score_pj": null' in text


def test_structured_context_missing_upstream_path_resolves_to_null() -> None:
    spec = SpecialistAgentSpec(
        name="test_agent",
        description="",
        prompt_name="agent.test",
        tools=(),
        output_schema=FinancialAnalysis,
        section_id="financial",
        inputs=(AgentInput(name="ebitda", type=VarType.MONEY_BRL, optional=True),),
    )
    ctx = _ctx(previous_outputs={"ocr": {"output": {}}})
    text = _render_context_for_prompt(
        ctx,
        spec=spec,
        config={"input_bindings": {"ebitda": "node.ocr.output.extracted_data.ebitda"}},
    )
    assert '"ebitda": null' in text


def test_structured_context_does_not_truncate_long_payloads() -> None:
    """Validates the main bug the structured path fixes: legacy truncates
    at 2000 chars/node, mid-field. Structured path passes only the named
    slot, never truncates."""
    spec = SpecialistAgentSpec(
        name="test_agent",
        description="",
        prompt_name="agent.test",
        tools=(),
        output_schema=FinancialAnalysis,
        section_id="financial",
        inputs=(AgentInput(name="resumo", type=VarType.STRING),),
    )
    long_value = "x" * 5000  # > 2000 chars (legacy would truncate)
    ctx = _ctx(previous_outputs={"upstream": {"output": {"resumo": long_value}}})
    text = _render_context_for_prompt(
        ctx, spec=spec, config={"input_bindings": {"resumo": "node.upstream.output.resumo"}}
    )
    # Full value should be present — no mid-string truncation.
    assert long_value in text


# ─── Legacy fallback path ─────────────────────────────────────────────────


def test_legacy_path_when_spec_has_no_inputs() -> None:
    spec = SpecialistAgentSpec(
        name="test_agent",
        description="",
        prompt_name="agent.test",
        tools=(),
        output_schema=FinancialAnalysis,
        section_id="financial",
        inputs=(),
    )
    ctx = _ctx(previous_outputs={"bureau": {"output": {"score_pj": 720}}})
    text = _render_context_for_prompt(ctx, spec=spec, config={})
    assert "[Outputs de nos anteriores]" in text
    assert "--- bureau ---" in text


def test_legacy_path_when_no_spec_passed() -> None:
    """Backward-compat: callers that don't pass `spec` continue to get the
    old text-dump behavior. (The runtime always passes spec now, but this
    lock the API contract.)"""
    ctx = _ctx(previous_outputs={"bureau": {"output": {"score_pj": 720}}})
    text = _render_context_for_prompt(ctx)
    assert "[Outputs de nos anteriores]" in text


def test_legacy_path_truncates_at_2000_chars_per_node() -> None:
    """Documents the known bug of the legacy path."""
    long_value = "y" * 3000
    ctx = _ctx(previous_outputs={"big": {"output": {"text": long_value}}})
    text = _render_context_for_prompt(ctx)
    # The legacy path's truncation hits before the full value is written.
    assert long_value not in text


# ─── SpecialistAgentNode.requires ─────────────────────────────────────────


def test_requires_emits_typed_requirement_per_bound_slot() -> None:
    """Use the real CATALOG entry for financial_analyst — it now declares
    4 inputs (cnpj/score_pj/endividamento_total/ebitda)."""
    spec = CATALOG["financial_analyst"]
    assert len(spec.inputs) >= 1, "fixture sanity: financial_analyst must declare inputs"

    bindings = {
        "cnpj": "trigger.cnpj",
        "score_pj": "node.bureau.output.score_pj",
        "endividamento_total": "node.bureau.output.endividamento_total",
        "ebitda": "node.ocr.output.extracted_data.ebitda",
    }
    node = SpecialistAgentNode(
        config={"agent": "financial_analyst", "input_bindings": bindings}
    )
    reqs = node.requires()
    by_name = {r.name: r for r in reqs}

    # One Requirement per declared input slot.
    assert set(by_name.keys()) == {slot.name for slot in spec.inputs}
    # Type + expr propagate.
    assert by_name["cnpj"].type == VarType.CNPJ
    assert by_name["cnpj"].expr == "{{trigger.cnpj}}"
    assert by_name["score_pj"].expr == "{{node.bureau.output.score_pj}}"
    assert by_name["score_pj"].optional is True


def test_requires_unbound_required_slot_produces_unbound_marker() -> None:
    """An unbound REQUIRED slot points at `__unbound__.<name>` so the graph
    validator surfaces 'missing upstream' for it."""
    spec = CATALOG["financial_analyst"]
    required_slots = [s for s in spec.inputs if not s.optional]
    assert required_slots, "fixture sanity: financial_analyst has at least 1 required slot"

    node = SpecialistAgentNode(
        config={"agent": "financial_analyst", "input_bindings": {}}
    )
    reqs = node.requires()
    by_name = {r.name: r for r in reqs}
    for slot in required_slots:
        req = by_name[slot.name]
        assert "__unbound__" in req.expr
        assert req.optional is False


def test_requires_returns_empty_when_agent_has_no_inputs() -> None:
    """Legacy agents (still on inputs=()) report no requirements; the
    runtime falls back to the text dump and the validator stays silent."""
    # social_contract_analyst not migrated yet, so inputs=().
    spec = CATALOG["social_contract_analyst"]
    assert spec.inputs == ()
    node = SpecialistAgentNode(config={"agent": "social_contract_analyst"})
    assert node.requires() == []


# ─── Catalog smoke ────────────────────────────────────────────────────────


def test_financial_analyst_declares_expected_phase_a_inputs() -> None:
    spec = CATALOG["financial_analyst"]
    names = {s.name for s in spec.inputs}
    assert {"cnpj", "score_pj", "endividamento_total", "ebitda"} <= names


def test_legal_analyst_declares_expected_inputs() -> None:
    spec = CATALOG["legal_analyst"]
    names = {s.name for s in spec.inputs}
    assert {
        "cnpj",
        "processos_total_qtd",
        "processos_ativos_valor_brl",
        "protestos_ativos_qtd",
    } <= names


def test_indebtedness_analyst_declares_expected_inputs() -> None:
    spec = CATALOG["indebtedness_analyst"]
    names = {s.name for s in spec.inputs}
    assert {
        "cnpj",
        "endividamento_total_brl",
        "scr_carteira_ativa_brl",
        "qtd_instituicoes_relacionamento",
    } <= names


def test_cross_reference_analyst_declares_synthesizer_inputs() -> None:
    """Synthesizer reads outputs of OTHER agents — slots refletem isso."""
    spec = CATALOG["cross_reference_analyst"]
    names = {s.name for s in spec.inputs}
    assert {
        "cnpj",
        "financial_summary",
        "financial_red_flags",
        "legal_summary",
        "legal_red_flags",
        "social_contract_red_flags",
        "partner_summary",
    } <= names


def test_other_agents_remain_on_legacy_path() -> None:
    """Phase A + esta fatia migram financial_analyst, legal_analyst,
    indebtedness_analyst e cross_reference_analyst. Os outros 6 ficam em
    inputs=() — graphs existentes continuam rodando sem mudanca."""
    legacy = [
        "social_contract_analyst",
        "partner_analyst",
        "commercial_visit_analyst",
        "opinion_writer",
        "document_extractor",
        "pleito_extractor",
    ]
    for name in legacy:
        assert CATALOG[name].inputs == (), (
            f"{name} mudou inesperadamente — esta fatia migra apenas "
            "financial_analyst, legal_analyst, indebtedness_analyst e "
            "cross_reference_analyst."
        )
