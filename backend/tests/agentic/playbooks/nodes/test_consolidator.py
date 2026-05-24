"""ConsolidatorNode — Phase 1 contract.

Covers:
- validate_config rejects malformed configs (missing fields, bad ops,
  wrong arity, unsupported `kind=function`, non-scalar literals,
  duplicate names, type-output mismatch).
- produces() collapses dotted names into top-level OBJECTs.
- requires() emits one Requirement per ref-arg.
- execute() applies each whitelisted op correctly, including null
  handling.
- execute() groups dotted names into nested objects.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agentic.playbooks.nodes._base import NodeContext, VarType
from app.agentic.playbooks.nodes.consolidator import ConsolidatorNode


def _ctx(previous_outputs: dict[str, dict] | None = None) -> NodeContext:
    return NodeContext(
        run_id=uuid4(),
        tenant_id=uuid4(),
        node_id="consolidador",
        initiated_by=None,
        previous_outputs=previous_outputs or {},
        trigger_data={},
    )


# ─── validate_config ──────────────────────────────────────────────────────


def test_validate_rejects_missing_output_fields() -> None:
    with pytest.raises(ValueError, match="output_fields"):
        ConsolidatorNode(config={})


def test_validate_rejects_empty_output_fields() -> None:
    with pytest.raises(ValueError, match="lista nao-vazia"):
        ConsolidatorNode(config={"output_fields": []})


def test_validate_rejects_duplicate_names() -> None:
    cfg = {
        "output_fields": [
            {"name": "x", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "literal", "value": 1}]},
            {"name": "x", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "literal", "value": 2}]},
        ]
    }
    with pytest.raises(ValueError, match="duplicado"):
        ConsolidatorNode(config=cfg)


def test_validate_rejects_unknown_op() -> None:
    cfg = {
        "output_fields": [
            {"name": "x", "type": "number", "op": "subtract",
             "args": [{"kind": "literal", "value": 1}]}
        ]
    }
    with pytest.raises(ValueError, match="whitelist"):
        ConsolidatorNode(config=cfg)


def test_validate_rejects_pegar_valor_with_two_args() -> None:
    cfg = {
        "output_fields": [
            {"name": "x", "type": "number", "op": "pegar_valor",
             "args": [
                 {"kind": "literal", "value": 1},
                 {"kind": "literal", "value": 2},
             ]}
        ]
    }
    with pytest.raises(ValueError, match="arg"):
        ConsolidatorNode(config=cfg)


def test_validate_rejects_function_kind_no_nesting_phase1() -> None:
    cfg = {
        "output_fields": [
            {"name": "x", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "function", "op": "min", "args": []}]}
        ]
    }
    with pytest.raises(ValueError, match="aninhamento"):
        ConsolidatorNode(config=cfg)


def test_validate_rejects_non_scalar_literal() -> None:
    cfg = {
        "output_fields": [
            {"name": "x", "type": "list", "op": "pegar_valor",
             "args": [{"kind": "literal", "value": [1, 2, 3]}]}
        ]
    }
    with pytest.raises(ValueError, match="escalar"):
        ConsolidatorNode(config=cfg)


def test_validate_rejects_ref_path_with_template_braces() -> None:
    cfg = {
        "output_fields": [
            {"name": "x", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "ref",
                       "path": "{{node.bureau.output.score}}"}]}
        ]
    }
    with pytest.raises(ValueError, match="chaves"):
        ConsolidatorNode(config=cfg)


def test_validate_rejects_invalid_field_name() -> None:
    cfg = {
        "output_fields": [
            {"name": "campo com espaco", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "literal", "value": 1}]}
        ]
    }
    with pytest.raises(ValueError, match="caracteres invalidos"):
        ConsolidatorNode(config=cfg)


def test_validate_rejects_dotted_name_with_empty_segment() -> None:
    cfg = {
        "output_fields": [
            {"name": "a..b", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "literal", "value": 1}]}
        ]
    }
    with pytest.raises(ValueError, match="vazios"):
        ConsolidatorNode(config=cfg)


def test_validate_rejects_concat_with_non_list_output_type() -> None:
    cfg = {
        "output_fields": [
            {"name": "x", "type": "number", "op": "concat",
             "args": [{"kind": "literal", "value": "a"}]}
        ]
    }
    with pytest.raises(ValueError, match="lista"):
        ConsolidatorNode(config=cfg)


def test_validate_rejects_min_with_non_numeric_output_type() -> None:
    cfg = {
        "output_fields": [
            {"name": "x", "type": "string", "op": "min",
             "args": [{"kind": "literal", "value": 1}]}
        ]
    }
    with pytest.raises(ValueError, match="number"):
        ConsolidatorNode(config=cfg)


# ─── produces() ───────────────────────────────────────────────────────────


def test_produces_plain_names_keep_their_type() -> None:
    cfg = {
        "output_fields": [
            {"name": "score", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "literal", "value": 1}]},
            {"name": "alertas", "type": "list", "op": "concat",
             "args": [{"kind": "literal", "value": "a"}]},
        ]
    }
    node = ConsolidatorNode(config=cfg)
    assert node.produces() == {
        "score": VarType.NUMBER,
        "alertas": VarType.LIST,
    }


def test_produces_dotted_names_collapse_to_top_level_object() -> None:
    cfg = {
        "output_fields": [
            {"name": "cabecalho.cnpj", "type": "cnpj", "op": "pegar_valor",
             "args": [{"kind": "literal", "value": "12345678000199"}]},
            {"name": "cabecalho.razao", "type": "string", "op": "pegar_valor",
             "args": [{"kind": "literal", "value": "Acme"}]},
            {"name": "scores.serasa", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "literal", "value": 720}]},
        ]
    }
    node = ConsolidatorNode(config=cfg)
    produced = node.produces()
    assert produced == {
        "cabecalho": VarType.OBJECT,
        "scores": VarType.OBJECT,
    }


# ─── requires() ───────────────────────────────────────────────────────────


def test_requires_one_per_ref_arg() -> None:
    cfg = {
        "output_fields": [
            {"name": "score", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "ref",
                       "path": "node.serasa.output.score_pj"}]},
            {"name": "alertas", "type": "list", "op": "concat",
             "args": [
                 {"kind": "ref", "path": "node.serasa.output.flags"},
                 {"kind": "ref", "path": "node.processos.output.flags"},
                 {"kind": "literal", "value": "literal_skip"},
             ]},
        ]
    }
    node = ConsolidatorNode(config=cfg)
    reqs = node.requires()
    assert len(reqs) == 3
    exprs = sorted(r.expr for r in reqs)
    assert exprs == [
        "{{node.processos.output.flags}}",
        "{{node.serasa.output.flags}}",
        "{{node.serasa.output.score_pj}}",
    ]


# ─── execute() — operacoes ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_pegar_valor_pulls_from_upstream() -> None:
    cfg = {
        "output_fields": [
            {"name": "score", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "ref",
                       "path": "node.serasa.output.score_pj"}]}
        ]
    }
    ctx = _ctx({"serasa": {"output": {"score_pj": 720}}})
    out = await ConsolidatorNode(config=cfg).execute(ctx, db=None)  # type: ignore[arg-type]
    assert out.data == {"score": 720}


@pytest.mark.asyncio
async def test_execute_min_ignores_null() -> None:
    cfg = {
        "output_fields": [
            {"name": "menor", "type": "number", "op": "min",
             "args": [
                 {"kind": "ref", "path": "node.a.output.score"},
                 {"kind": "ref", "path": "node.b.output.score"},
                 {"kind": "ref", "path": "node.c.output.score"},
             ]}
        ]
    }
    ctx = _ctx({
        "a": {"output": {"score": 800}},
        "b": {"output": {"score": None}},
        "c": {"output": {"score": 600}},
    })
    out = await ConsolidatorNode(config=cfg).execute(ctx, db=None)  # type: ignore[arg-type]
    assert out.data == {"menor": 600}


@pytest.mark.asyncio
async def test_execute_max_with_all_null_returns_null() -> None:
    cfg = {
        "output_fields": [
            {"name": "maior", "type": "number", "op": "max",
             "args": [
                 {"kind": "ref", "path": "node.a.output.x"},
                 {"kind": "ref", "path": "node.b.output.x"},
             ]}
        ]
    }
    ctx = _ctx({
        "a": {"output": {"x": None}},
        "b": {"output": {"x": None}},
    })
    out = await ConsolidatorNode(config=cfg).execute(ctx, db=None)  # type: ignore[arg-type]
    assert out.data == {"maior": None}


@pytest.mark.asyncio
async def test_execute_sum_of_all_null_returns_zero() -> None:
    cfg = {
        "output_fields": [
            {"name": "total", "type": "number", "op": "sum",
             "args": [
                 {"kind": "ref", "path": "node.a.output.x"},
                 {"kind": "ref", "path": "node.b.output.x"},
             ]}
        ]
    }
    ctx = _ctx({
        "a": {"output": {"x": None}},
        "b": {"output": {"x": None}},
    })
    out = await ConsolidatorNode(config=cfg).execute(ctx, db=None)  # type: ignore[arg-type]
    assert out.data == {"total": 0}


@pytest.mark.asyncio
async def test_execute_avg_ignores_null() -> None:
    cfg = {
        "output_fields": [
            {"name": "media", "type": "number", "op": "avg",
             "args": [
                 {"kind": "ref", "path": "node.a.output.x"},
                 {"kind": "ref", "path": "node.b.output.x"},
                 {"kind": "ref", "path": "node.c.output.x"},
             ]}
        ]
    }
    ctx = _ctx({
        "a": {"output": {"x": 10}},
        "b": {"output": {"x": None}},
        "c": {"output": {"x": 30}},
    })
    out = await ConsolidatorNode(config=cfg).execute(ctx, db=None)  # type: ignore[arg-type]
    assert out.data == {"media": 20}


@pytest.mark.asyncio
async def test_execute_concat_skips_null_and_flattens_lists() -> None:
    cfg = {
        "output_fields": [
            {"name": "alertas", "type": "list", "op": "concat",
             "args": [
                 {"kind": "ref", "path": "node.a.output.flags"},
                 {"kind": "ref", "path": "node.b.output.flags"},
                 {"kind": "ref", "path": "node.c.output.flags"},
             ]}
        ]
    }
    ctx = _ctx({
        "a": {"output": {"flags": ["alto_endividamento"]}},
        "b": {"output": {"flags": None}},
        "c": {"output": {"flags": ["processos_ativos", "atraso"]}},
    })
    out = await ConsolidatorNode(config=cfg).execute(ctx, db=None)  # type: ignore[arg-type]
    assert out.data == {
        "alertas": ["alto_endividamento", "processos_ativos", "atraso"]
    }


@pytest.mark.asyncio
async def test_execute_coalesce_returns_first_non_null() -> None:
    cfg = {
        "output_fields": [
            {"name": "score", "type": "number", "op": "coalesce",
             "args": [
                 {"kind": "ref", "path": "node.preferred.output.score"},
                 {"kind": "ref", "path": "node.fallback.output.score"},
                 {"kind": "literal", "value": 500},
             ]}
        ]
    }
    ctx = _ctx({
        "preferred": {"output": {"score": None}},
        "fallback": {"output": {"score": 720}},
    })
    out = await ConsolidatorNode(config=cfg).execute(ctx, db=None)  # type: ignore[arg-type]
    assert out.data == {"score": 720}


@pytest.mark.asyncio
async def test_execute_coalesce_falls_to_literal_when_all_refs_null() -> None:
    cfg = {
        "output_fields": [
            {"name": "score", "type": "number", "op": "coalesce",
             "args": [
                 {"kind": "ref", "path": "node.a.output.score"},
                 {"kind": "ref", "path": "node.b.output.score"},
                 {"kind": "literal", "value": 500},
             ]}
        ]
    }
    ctx = _ctx({
        "a": {"output": {"score": None}},
        "b": {"output": {"score": None}},
    })
    out = await ConsolidatorNode(config=cfg).execute(ctx, db=None)  # type: ignore[arg-type]
    assert out.data == {"score": 500}


@pytest.mark.asyncio
async def test_execute_len_counts_list() -> None:
    cfg = {
        "output_fields": [
            {"name": "qtd", "type": "number", "op": "len",
             "args": [{"kind": "ref", "path": "node.a.output.flags"}]}
        ]
    }
    ctx = _ctx({"a": {"output": {"flags": ["x", "y", "z"]}}})
    out = await ConsolidatorNode(config=cfg).execute(ctx, db=None)  # type: ignore[arg-type]
    assert out.data == {"qtd": 3}


@pytest.mark.asyncio
async def test_execute_len_of_null_is_zero() -> None:
    cfg = {
        "output_fields": [
            {"name": "qtd", "type": "number", "op": "len",
             "args": [{"kind": "ref", "path": "node.a.output.flags"}]}
        ]
    }
    ctx = _ctx({"a": {"output": {"flags": None}}})
    out = await ConsolidatorNode(config=cfg).execute(ctx, db=None)  # type: ignore[arg-type]
    assert out.data == {"qtd": 0}


# ─── execute() — nesting via dotted names ─────────────────────────────────


@pytest.mark.asyncio
async def test_execute_groups_dotted_names_into_nested_objects() -> None:
    cfg = {
        "output_fields": [
            {"name": "cabecalho.cnpj", "type": "cnpj", "op": "pegar_valor",
             "args": [{"kind": "ref",
                       "path": "trigger.cnpj"}]},
            {"name": "cabecalho.razao", "type": "string", "op": "pegar_valor",
             "args": [{"kind": "ref",
                       "path": "node.serasa.output.razao_social"}]},
            {"name": "scores.serasa", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "ref",
                       "path": "node.serasa.output.score_pj"}]},
            {"name": "scores.bigdata", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "ref",
                       "path": "node.bigdata.output.score"}]},
            {"name": "alertas", "type": "list", "op": "concat",
             "args": [{"kind": "ref",
                       "path": "node.serasa.output.flags"}]},
        ]
    }
    ctx = NodeContext(
        run_id=uuid4(),
        tenant_id=uuid4(),
        node_id="consolidador",
        initiated_by=None,
        previous_outputs={
            "serasa": {"output": {
                "score_pj": 720,
                "razao_social": "Acme LTDA",
                "flags": ["ativo"],
            }},
            "bigdata": {"output": {"score": 680}},
        },
        trigger_data={"cnpj": "12345678000199"},
    )
    out = await ConsolidatorNode(config=cfg).execute(ctx, db=None)  # type: ignore[arg-type]
    assert out.data == {
        "cabecalho": {
            "cnpj": "12345678000199",
            "razao": "Acme LTDA",
        },
        "scores": {
            "serasa": 720,
            "bigdata": 680,
        },
        "alertas": ["ativo"],
    }


# ─── execute() — type coercion ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_coerces_numeric_string_to_number() -> None:
    cfg = {
        "output_fields": [
            {"name": "score", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "ref",
                       "path": "node.x.output.value_as_string"}]}
        ]
    }
    ctx = _ctx({"x": {"output": {"value_as_string": "720"}}})
    out = await ConsolidatorNode(config=cfg).execute(ctx, db=None)  # type: ignore[arg-type]
    assert out.data == {"score": 720}
    assert isinstance(out.data["score"], int)


@pytest.mark.asyncio
async def test_execute_returns_status_hint() -> None:
    cfg = {
        "output_fields": [
            {"name": "x", "type": "number", "op": "pegar_valor",
             "args": [{"kind": "literal", "value": 1}]}
        ]
    }
    out = await ConsolidatorNode(config=cfg).execute(_ctx(), db=None)  # type: ignore[arg-type]
    assert out.status_hint == "Consolidou 1 campo(s)"
