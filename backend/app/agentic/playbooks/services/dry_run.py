"""Dry-run service — execute a workflow graph in SANDBOX mode.

Differences vs the real engine:
- Does NOT call external services (no Serasa HTTP, no Anthropic).
- Does NOT persist anything (no DB writes for dossier, run, node_run, etc).
- Each node's output is FAKED based on its `produces()` declaration —
  one mock value per VarType (cf. `_MOCK_BY_TYPE`).
- Order is the same topological walk used by the real engine, so the
  user sees exactly which nodes run in which sequence + ramo de erro.
- Edge conditions ARE evaluated against the mock outputs (so branches
  behave realistically, not "everything passes").

Use case: editor "Testar" button. The analyst types a `trigger_data`
JSON, hits run, sees a step-by-step replay (label, output, duration
sintética). Lets them validate the wiring before creating a real
dossier and burning a paid bureau request.

Pause behavior: human_input nodes are auto-resumed with mock values
matching the form fields (so dry-run doesn't block waiting for human).
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.agentic.playbooks.nodes._base import VarType
from app.agentic.playbooks.nodes.registry import NODE_TYPES, get_node_class
from app.agentic.playbooks.schemas.definition import NodeSpec, PlaybookGraph
from app.agentic.playbooks.services.resolver import (
    evaluate_edge_condition,
    resolve_templates,
)

__all__ = [
    "DryRunResult",
    "DryRunStep",
    "dry_run_workflow",
]


@dataclass(slots=True)
class DryRunStep:
    """One node's outcome during dry-run."""

    node_id: str
    node_type: str
    label: str
    status: str               # "completed" | "failed" | "skipped" | "unavailable"
    output: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0       # synthetic — small constant per node type
    error: str | None = None


@dataclass(slots=True)
class DryRunResult:
    final_status: str          # "completed" | "failed"
    steps: list[DryRunStep] = field(default_factory=list)
    error: str | None = None   # set when an early failure aborted the run


# ─── Mock value factory ──────────────────────────────────────────────────

# Sintetiza valores realistas pra cada VarType. Os valores SÃO usados
# pra avaliar edge conditions, então precisam ser tipados (não placeholders
# string em todo lugar).
_MOCK_BY_TYPE: dict[VarType, Any] = {
    VarType.STRING: "exemplo",
    VarType.CPF: "12345678901",
    VarType.CNPJ: "46802619000110",
    VarType.EMAIL: "exemplo@empresa.com.br",
    VarType.PHONE: "11999990000",
    VarType.DATE: "2026-01-01",
    VarType.DATETIME: "2026-01-01T12:00:00Z",
    VarType.NUMBER: 123,
    VarType.MONEY_BRL: 1000.0,
    VarType.SCORE: 720,
    VarType.BOOLEAN: True,
    VarType.URL: "https://example.com",
    VarType.UUID_T: "00000000-0000-0000-0000-000000000000",
    VarType.FILE: "mock://file.pdf",
    VarType.OBJECT: {"_": "mock_object"},
    VarType.LIST: [],
}

# Tempo sintético por tipo (ms) — ajuda o usuário a entender a ordem de
# grandeza relativa de cada etapa.
_DURATION_BY_NODE_TYPE: dict[str, int] = {
    "trigger": 5,
    "human_input": 30,
    "human_review": 30,
    "document_request": 30,
    "document_extractor": 1500,
    "bureau_query": 4000,
    "specialist_agent": 25000,
    "conditional_branch": 5,
    "http_request": 800,
    "notification": 50,
    "output_generator": 200,
}
_DEFAULT_DURATION_MS = 100


def _mock_value(vartype_str: str) -> Any:
    """Lookup mock por nome do tipo (string vinda do produces serializado)."""
    try:
        vt = VarType(vartype_str)
    except ValueError:
        return None
    return _MOCK_BY_TYPE.get(vt)


# ─── Topological walk (cópia leve do engine) ─────────────────────────────


def _topological_order(graph: PlaybookGraph) -> list[NodeSpec]:
    in_degree: dict[str, int] = defaultdict(int)
    children: dict[str, list[str]] = defaultdict(list)
    by_id: dict[str, NodeSpec] = {n.id: n for n in graph.nodes}
    for n in graph.nodes:
        in_degree[n.id] = 0
    for e in graph.edges:
        if e.source in by_id and e.target in by_id:
            in_degree[e.target] += 1
            children[e.source].append(e.target)
    queue = sorted([nid for nid, d in in_degree.items() if d == 0])
    out: list[NodeSpec] = []
    while queue:
        nid = queue.pop(0)
        out.append(by_id[nid])
        for c in sorted(children[nid]):
            in_degree[c] -= 1
            if in_degree[c] == 0:
                queue.append(c)
        queue.sort()
    for n in graph.nodes:
        if n not in out:
            out.append(n)
    return out


# ─── Main entry ──────────────────────────────────────────────────────────


def dry_run_workflow(
    graph: PlaybookGraph,
    *,
    trigger_data: dict[str, Any] | None = None,
) -> DryRunResult:
    """Execute the graph in sandbox mode and return per-node outcomes.

    Doesn't touch DB or external services. Outputs are derived from each
    node's `produces()` declaration via `_MOCK_BY_TYPE`. Edge conditions
    are evaluated against mocks, so branches behave correctly.

    `trigger_data` is the user-supplied seed (typically `{cnpj: ...}`).
    """
    trigger_data = trigger_data or {}
    ordered = _topological_order(graph)

    # Track outputs accumulated so far — feeds the resolver for templates
    # in downstream node configs and edge conditions.
    context_data: dict[str, dict[str, Any]] = {}
    skipped_ids: set[str] = set()
    settled_ids: set[str] = set()
    steps: list[DryRunStep] = []

    for node in ordered:
        node_label = node.label or node.type or node.id

        # 1. Skip rule: if all incoming sources are skipped, this is too.
        incoming = [e for e in graph.edges if e.target == node.id]
        if incoming and all(e.source in skipped_ids for e in incoming):
            steps.append(
                DryRunStep(
                    node_id=node.id,
                    node_type=node.type,
                    label=node_label,
                    status="skipped",
                    error="Todos os caminhos anteriores foram pulados.",
                )
            )
            skipped_ids.add(node.id)
            settled_ids.add(node.id)
            continue

        # 2. Edge conditions: any incoming edge passes? (no cond = passes)
        if incoming:
            ctx_for_eval = {"trigger": trigger_data, "node": context_data}
            reachable = False
            for e in incoming:
                if e.source in skipped_ids:
                    continue
                if e.source not in settled_ids:
                    continue
                if not e.condition or evaluate_edge_condition(e.condition, ctx_for_eval):
                    reachable = True
                    break
            if not reachable:
                steps.append(
                    DryRunStep(
                        node_id=node.id,
                        node_type=node.type,
                        label=node_label,
                        status="skipped",
                        error="Nenhuma condição de entrada foi satisfeita.",
                    )
                )
                skipped_ids.add(node.id)
                settled_ids.add(node.id)
                continue

        # 3. Available? available=False = mostra como "unavailable" mas
        # sintetiza output como se tivesse rodado (pra downstream não
        # cascatear skips em produção).
        meta = NODE_TYPES.get(node.type)
        if meta is None:
            steps.append(
                DryRunStep(
                    node_id=node.id,
                    node_type=node.type,
                    label=node_label,
                    status="failed",
                    error=f"Tipo de nó '{node.type}' não registrado.",
                )
            )
            settled_ids.add(node.id)
            continue

        if not meta.available:
            mock_output = _mock_output_for(node, trigger_data)
            steps.append(
                DryRunStep(
                    node_id=node.id,
                    node_type=node.type,
                    label=node_label,
                    status="unavailable",
                    output=mock_output,
                    duration_ms=_DURATION_BY_NODE_TYPE.get(node.type, _DEFAULT_DURATION_MS),
                    error=(
                        "Tipo marcado como 'em breve' — output simulado pra "
                        "permitir testar o fluxo, mas não vai rodar de verdade."
                    ),
                )
            )
            context_data[node.id] = {"output": mock_output}
            settled_ids.add(node.id)
            continue

        # 4. Resolve config (templates) e validate.
        resolve_context = {"trigger": trigger_data, "node": context_data}
        resolved_config = resolve_templates(node.config or {}, resolve_context)

        try:
            cls = get_node_class(node.type)
            instance = cls(resolved_config)
        except Exception as exc:
            steps.append(
                DryRunStep(
                    node_id=node.id,
                    node_type=node.type,
                    label=node_label,
                    status="failed",
                    error=f"Configuração inválida: {exc}",
                )
            )
            settled_ids.add(node.id)
            continue

        # 5. Trigger node: emite o trigger_data como output literal.
        if node.type == "trigger":
            output = {"trigger_kind": resolved_config.get("kind", "manual"), **trigger_data}
        else:
            # Mock output baseado em produces().
            output = _mock_output_for(node, trigger_data, instance=instance)

        # 6. Special-case conditional_branch: avalia a expressão real contra
        # context atual pra decidir true/false (afeta edges downstream).
        if node.type == "conditional_branch":
            expr = resolved_config.get("expression")
            if isinstance(expr, str) and expr.strip():
                try:
                    result = evaluate_edge_condition(expr, resolve_context)
                except Exception as exc:
                    output = {"result": False, "error": str(exc)}
                else:
                    output = {"result": result, "expression": expr, "evaluated": True}

        steps.append(
            DryRunStep(
                node_id=node.id,
                node_type=node.type,
                label=node_label,
                status="completed",
                output=output,
                duration_ms=_DURATION_BY_NODE_TYPE.get(node.type, _DEFAULT_DURATION_MS),
            )
        )
        context_data[node.id] = {"output": output}
        settled_ids.add(node.id)

    failed = any(s.status == "failed" for s in steps)
    return DryRunResult(
        final_status="failed" if failed else "completed",
        steps=steps,
    )


def _mock_output_for(
    node: NodeSpec,
    trigger_data: dict[str, Any],
    *,
    instance: Any | None = None,
) -> dict[str, Any]:
    """Build a fake `output.data` baseado em produces() do nó.

    Para trigger, propaga trigger_data. Para human_input, sintetiza um
    valor por field do form. Para o resto, usa `_MOCK_BY_TYPE` por
    cada VarType declarado em produces().
    """
    if node.type == "trigger":
        return {"trigger_kind": (node.config or {}).get("kind", "manual"), **trigger_data}

    if node.type == "human_input":
        # Sintetiza valores por field — usa trigger_data se mesmo nome.
        out: dict[str, Any] = {}
        for f in (node.config or {}).get("fields") or []:
            key = f.get("key")
            if not isinstance(key, str) or not key:
                continue
            if key in trigger_data:
                out[key] = trigger_data[key]
                continue
            ftype = f.get("type", "string")
            try:
                vt = {
                    "cnpj": VarType.CNPJ,
                    "cpf": VarType.CPF,
                    "email": VarType.EMAIL,
                    "number": VarType.NUMBER,
                    "date": VarType.DATE,
                    "boolean": VarType.BOOLEAN,
                    "json": VarType.OBJECT,
                }.get(ftype, VarType.STRING)
            except KeyError:
                vt = VarType.STRING
            out[key] = _MOCK_BY_TYPE[vt]
        return out

    # Caso geral: usa produces() do instance (já criado com config resolved).
    if instance is None:
        try:
            instance = get_node_class(node.type)(node.config or {})
        except Exception:
            return {}
    try:
        produced = instance.produces()
    except Exception:
        return {}
    out_general: dict[str, Any] = {}
    for var_name, var_type in produced.items():
        if var_name in trigger_data:
            out_general[var_name] = trigger_data[var_name]
        else:
            mock = _MOCK_BY_TYPE.get(var_type)
            # uuid muito previsível mascara bugs — gera novo por chamada.
            if var_type == VarType.UUID_T:
                mock = str(uuid4())
            out_general[var_name] = mock
    return out_general


# Avoid unused warning on the time import — kept for future per-node timing.
_ = time
