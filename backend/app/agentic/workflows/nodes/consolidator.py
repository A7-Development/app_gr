"""ConsolidatorNode — deterministic data merger for fan-in.

When 2+ upstream nodes feed into a node that needs to combine their data
(without invoking an LLM), use the consolidator. It applies a whitelisted
set of functions (`pegar_valor`, `min`, `max`, `sum`, `avg`, `concat`,
`coalesce`, `len`) over named refs to upstream outputs and/or scalar
literals, producing a structured object whose shape the user declared.

Phase 1 contract:
- Flat-only: each output field is ONE function call. No nesting of function
  calls. Combinations (e.g. `A - B*C`) are achieved by chaining consolidators.
- Args are `{kind: "ref", path}` (resolved via the engine's template
  resolver) or `{kind: "literal", value}` (scalar number / string / boolean).
  No list / object literals — for lists, pull from upstream.
- Output field names may use dotted notation (`cabecalho.cnpj`,
  `scores.serasa_pj`) to produce nested OBJECT outputs. The engine groups
  by dot at execute() time. `produces()` returns the top-level OBJECT keys.
- No conditional logic (`if`) in the function set. For routing/conditional
  emission, branch with a `conditional_branch` upstream and converge.

Null handling (documented in glossary; analyst expectation):
- `min`, `max`, `sum`, `avg`, `len` ignore null values.
- `sum` of all-null returns 0; `avg`/`min`/`max`/`len` of all-null return null.
- `concat` skips null entries (does NOT treat them as empty list).
- `coalesce` returns the first non-null arg; null if all are null.
- `pegar_valor` passes through (null in -> null out).

Config shape:
    {
      "output_fields": [
        {
          "name": "score_consolidado",
          "type": "number",
          "op": "pegar_valor",
          "args": [
            {"kind": "ref", "path": "node.bureau_serasa.output.score_pj"}
          ]
        },
        {
          "name": "alertas",
          "type": "list",
          "op": "concat",
          "args": [
            {"kind": "ref", "path": "node.bureau_serasa.output.flags"},
            {"kind": "ref", "path": "node.processos.output.flags"}
          ]
        },
        {
          "name": "evidencias.balanco_doc_id",
          "type": "string",
          "op": "pegar_valor",
          "args": [
            {"kind": "ref", "path": "node.ocr_balanco.output.document_id"}
          ]
        }
      ]
    }

Output shape (for the example above):
    {
      "score_consolidado": 720,
      "alertas": ["alto_endividamento", "processos_ativos"],
      "evidencias": {"balanco_doc_id": "doc_abc123"}
    }
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from statistics import mean
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.workflows.nodes._base import (
    BaseNode,
    NodeContext,
    NodeOutput,
    Requirement,
    VarType,
)
from app.agentic.workflows.services.resolver import resolve_templates


class ConsolidatorOp(StrEnum):
    PEGAR_VALOR = "pegar_valor"
    MIN = "min"
    MAX = "max"
    SUM = "sum"
    AVG = "avg"
    CONCAT = "concat"
    COALESCE = "coalesce"
    LEN = "len"


# Op -> (min_args, max_args | None for unbounded). PEGAR_VALOR / LEN take
# exactly 1 arg; the others take 1+ (variadic).
_OP_ARITY: dict[ConsolidatorOp, tuple[int, int | None]] = {
    ConsolidatorOp.PEGAR_VALOR: (1, 1),
    ConsolidatorOp.MIN: (1, None),
    ConsolidatorOp.MAX: (1, None),
    ConsolidatorOp.SUM: (1, None),
    ConsolidatorOp.AVG: (1, None),
    ConsolidatorOp.CONCAT: (1, None),
    ConsolidatorOp.COALESCE: (1, None),
    ConsolidatorOp.LEN: (1, 1),
}

# Numeric ops require all args resolve to numbers (or null).
_NUMERIC_OPS = {
    ConsolidatorOp.MIN,
    ConsolidatorOp.MAX,
    ConsolidatorOp.SUM,
    ConsolidatorOp.AVG,
}

# Ops whose output type is fixed regardless of inputs. (Others infer from
# the args — e.g. PEGAR_VALOR / COALESCE take the type from the args.)
_OP_OUTPUT_TYPE: dict[ConsolidatorOp, VarType | None] = {
    ConsolidatorOp.PEGAR_VALOR: None,
    ConsolidatorOp.MIN: VarType.NUMBER,
    ConsolidatorOp.MAX: VarType.NUMBER,
    ConsolidatorOp.SUM: VarType.NUMBER,
    ConsolidatorOp.AVG: VarType.NUMBER,
    ConsolidatorOp.CONCAT: VarType.LIST,
    ConsolidatorOp.COALESCE: None,
    ConsolidatorOp.LEN: VarType.NUMBER,
}


# Types compatible as "number" outputs (for validate_config type checking).
_NUMERIC_TYPES = {
    VarType.NUMBER,
    VarType.SCORE,
    VarType.MONEY_BRL,
}


class ConsolidatorNode(BaseNode):
    """Deterministic merge node — combines outputs of N upstream nodes.

    Zero LLM calls. Pure-Python evaluator over a whitelisted function set.
    Output is fully reproducible: same inputs always yield same outputs
    (auditable, cacheable).
    """

    type = "consolidator"

    # ─── Validation ───────────────────────────────────────────────────────

    def validate_config(self) -> None:
        fields = self.config.get("output_fields")
        if not isinstance(fields, list) or not fields:
            raise ValueError(
                "consolidator: `output_fields` deve ser uma lista nao-vazia."
            )

        seen_names: set[str] = set()
        for idx, field in enumerate(fields):
            if not isinstance(field, dict):
                raise ValueError(
                    f"consolidator.output_fields[{idx}] deve ser objeto."
                )

            name = field.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    f"consolidator.output_fields[{idx}].name e obrigatorio."
                )
            if name in seen_names:
                raise ValueError(
                    f"consolidator: nome de saida duplicado '{name}'."
                )
            seen_names.add(name)
            _validate_field_name(name, idx)

            type_str = field.get("type")
            try:
                field_type = VarType(type_str)
            except ValueError:
                raise ValueError(
                    f"consolidator.output_fields[{idx}].type "
                    f"'{type_str}' nao e VarType valido."
                ) from None

            op_str = field.get("op")
            try:
                op = ConsolidatorOp(op_str)
            except ValueError:
                raise ValueError(
                    f"consolidator.output_fields[{idx}].op '{op_str}' "
                    f"nao esta na whitelist. "
                    f"Use uma de: {sorted(o.value for o in ConsolidatorOp)}."
                ) from None

            args = field.get("args")
            if not isinstance(args, list) or not args:
                raise ValueError(
                    f"consolidator.output_fields[{idx}].args "
                    "deve ser lista nao-vazia."
                )
            min_arity, max_arity = _OP_ARITY[op]
            if len(args) < min_arity or (
                max_arity is not None and len(args) > max_arity
            ):
                expected = (
                    f"{min_arity}"
                    if max_arity == min_arity
                    else f">= {min_arity}"
                    if max_arity is None
                    else f"{min_arity}..{max_arity}"
                )
                raise ValueError(
                    f"consolidator.output_fields[{idx}].op '{op.value}' "
                    f"requer {expected} arg(s); recebeu {len(args)}."
                )

            for a_idx, arg in enumerate(args):
                _validate_arg(arg, op_path=f"output_fields[{idx}].args[{a_idx}]")

            # Output type compatibility check (fail-fast at save time).
            fixed_type = _OP_OUTPUT_TYPE[op]
            if fixed_type is VarType.NUMBER and field_type not in _NUMERIC_TYPES:
                raise ValueError(
                    f"consolidator.output_fields[{idx}]: op '{op.value}' "
                    f"produz number mas o campo declara tipo "
                    f"'{field_type.value}'. Use number/score/money_brl."
                )
            if fixed_type is VarType.LIST and field_type != VarType.LIST:
                raise ValueError(
                    f"consolidator.output_fields[{idx}]: op '{op.value}' "
                    f"produz lista mas o campo declara tipo "
                    f"'{field_type.value}'. Use list."
                )

    # ─── Contracts ────────────────────────────────────────────────────────

    def produces(self) -> dict[str, VarType]:
        """Top-level output keys with their VarType.

        Dotted names (e.g. `cabecalho.cnpj`) collapse to the top-level key
        (`cabecalho`) typed as OBJECT — downstream sees a nested object.
        Plain names map directly to their declared type.
        """
        out: dict[str, VarType] = {}
        for field in self.config.get("output_fields", []):
            if not isinstance(field, dict):
                continue
            name = field.get("name")
            if not isinstance(name, str):
                continue
            top, has_dot = _split_top(name)
            if has_dot:
                # Multiple dotted fields under same top → still OBJECT, no clash.
                out[top] = VarType.OBJECT
            else:
                try:
                    out[top] = VarType(field.get("type"))
                except ValueError:
                    continue
        return out

    def requires(self) -> list[Requirement]:
        """One Requirement per `kind=ref` arg.

        We can't infer a precise expected type per ref without per-op
        rules — Phase 1 declares `STRING` (the wildcard sink) and lets the
        runtime resolver deliver whatever's there. Type-strictness at the
        consumer side is a Phase 2 sharpening (per-op type inference).
        """
        reqs: list[Requirement] = []
        for f_idx, field in enumerate(self.config.get("output_fields", [])):
            if not isinstance(field, dict):
                continue
            args = field.get("args") or []
            for a_idx, arg in enumerate(args):
                if not isinstance(arg, dict) or arg.get("kind") != "ref":
                    continue
                path = arg.get("path")
                if not isinstance(path, str):
                    continue
                expr = _path_to_template_expr(path)
                if expr is None:
                    continue
                reqs.append(
                    Requirement(
                        name=f"{field.get('name', f'field_{f_idx}')}#arg{a_idx}",
                        type=VarType.STRING,
                        expr=expr,
                        optional=False,
                    )
                )
        return reqs

    # ─── Execution ────────────────────────────────────────────────────────

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        resolve_ctx = {
            "trigger": ctx.trigger_data or {},
            "node": ctx.previous_outputs or {},
        }

        flat: dict[str, Any] = {}
        for field in self.config["output_fields"]:
            name = field["name"]
            op = ConsolidatorOp(field["op"])
            resolved_args = [
                _resolve_arg(arg, resolve_ctx) for arg in field["args"]
            ]
            value = _apply_op(op, resolved_args)
            flat[name] = _coerce_to_type(value, VarType(field["type"]))

        # Group dotted names into nested objects.
        nested = _nest(flat)
        return NodeOutput(
            data=nested,
            status_hint=f"Consolidou {len(self.config['output_fields'])} campo(s)",
        )


# ─── Helpers ──────────────────────────────────────────────────────────────


def _validate_field_name(name: str, idx: int) -> None:
    """Each segment between dots must be a valid identifier (no empty parts)."""
    if name.startswith(".") or name.endswith(".") or ".." in name:
        raise ValueError(
            f"consolidator.output_fields[{idx}].name '{name}' tem segmentos "
            "vazios separados por ponto."
        )
    for seg in name.split("."):
        if not seg or not _is_safe_segment(seg):
            raise ValueError(
                f"consolidator.output_fields[{idx}].name '{name}' contem "
                "caracteres invalidos. Use letras, numeros e underscore "
                "(separados por ponto)."
            )


def _is_safe_segment(s: str) -> bool:
    return s.replace("_", "").isalnum() and not s[0].isdigit()


def _validate_arg(arg: Any, *, op_path: str) -> None:
    if not isinstance(arg, dict):
        raise ValueError(f"consolidator.{op_path} deve ser objeto.")
    kind = arg.get("kind")
    if kind == "ref":
        path = arg.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(
                f"consolidator.{op_path}.path e obrigatorio quando kind=ref."
            )
        if "{{" in path or "}}" in path:
            raise ValueError(
                f"consolidator.{op_path}.path nao deve conter chaves "
                "`{{ }}` — informe so o caminho (ex.: "
                "'node.bureau.output.score_pj')."
            )
    elif kind == "literal":
        if "value" not in arg:
            raise ValueError(
                f"consolidator.{op_path}.value e obrigatorio quando kind=literal."
            )
        value = arg["value"]
        # Phase 1: scalars only (no list/object literals).
        if not isinstance(value, (int, float, str, bool)):
            raise ValueError(
                f"consolidator.{op_path}.value deve ser escalar "
                "(number, string ou boolean) na Fase 1."
            )
    elif kind == "function":
        raise ValueError(
            f"consolidator.{op_path}.kind=function nao e suportado na "
            "Fase 1 (sem aninhamento). Encadeie consolidators para combinar."
        )
    else:
        raise ValueError(
            f"consolidator.{op_path}.kind invalido: '{kind}'. "
            "Use 'ref' ou 'literal'."
        )


def _path_to_template_expr(path: str) -> str | None:
    """Convert `node.X.output.Y` or `trigger.Y` to the expr form used by
    the validator (`{{node.X.output.Y}}`).
    """
    p = path.strip()
    if not p:
        return None
    return "{{" + p + "}}"


def _resolve_arg(arg: dict[str, Any], context: dict[str, Any]) -> Any:
    if arg.get("kind") == "literal":
        return arg.get("value")
    # ref
    return resolve_templates("{{" + arg["path"] + "}}", context)


def _split_top(name: str) -> tuple[str, bool]:
    """Return (top_segment, has_dots)."""
    if "." in name:
        return name.split(".", 1)[0], True
    return name, False


def _nest(flat: dict[str, Any]) -> dict[str, Any]:
    """Group dotted keys into nested dicts.

    {"a.b.c": 1, "a.b.d": 2, "x": 9} -> {"a": {"b": {"c": 1, "d": 2}}, "x": 9}
    """
    out: dict[str, Any] = {}
    for key, value in flat.items():
        if "." not in key:
            out[key] = value
            continue
        parts = key.split(".")
        cursor = out
        for part in parts[:-1]:
            existing = cursor.get(part)
            if not isinstance(existing, dict):
                existing = {}
                cursor[part] = existing
            cursor = existing
        cursor[parts[-1]] = value
    return out


def _apply_op(op: ConsolidatorOp, args: list[Any]) -> Any:
    if op == ConsolidatorOp.PEGAR_VALOR:
        return args[0]
    if op == ConsolidatorOp.LEN:
        v = args[0]
        if v is None:
            return 0
        if isinstance(v, (list, tuple, str, dict)):
            return len(v)
        return 0
    if op == ConsolidatorOp.COALESCE:
        for a in args:
            if a is not None:
                return a
        return None
    if op == ConsolidatorOp.CONCAT:
        out: list[Any] = []
        for a in args:
            if a is None:
                continue
            if isinstance(a, list):
                out.extend(a)
            else:
                # Non-list non-null: append as scalar.
                out.append(a)
        return out
    if op in _NUMERIC_OPS:
        nums = [_to_number(a) for a in args if a is not None]
        nums = [n for n in nums if n is not None]
        if not nums:
            return 0 if op == ConsolidatorOp.SUM else None
        if op == ConsolidatorOp.MIN:
            return min(nums)
        if op == ConsolidatorOp.MAX:
            return max(nums)
        if op == ConsolidatorOp.SUM:
            return sum(nums)
        if op == ConsolidatorOp.AVG:
            return mean(nums)
    raise ValueError(f"consolidator: op '{op}' nao implementada.")


def _to_number(v: Any) -> float | int | None:
    if isinstance(v, bool):
        # bool is subtype of int in Python — explicit reject to avoid surprise.
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            if "." in v or "e" in v.lower():
                return float(v)
            return int(v)
        except ValueError:
            return None
    return None


def _coerce_to_type(value: Any, declared: VarType) -> Any:
    """Light coercion to fit the declared output type. Lossy on purpose —
    if the analyst said `number` and the op produced a string '720', we
    parse to 720; if it produced a list, we leave it (validator should
    have caught at save time).
    """
    if value is None:
        return None
    if declared in _NUMERIC_TYPES:
        n = _to_number(value)
        return n if n is not None else value
    if declared == VarType.STRING:
        if isinstance(value, str):
            return value
        return str(value)
    if declared == VarType.BOOLEAN:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "sim"}
        return bool(value)
    if declared == VarType.LIST:
        if isinstance(value, list):
            return value
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
            return list(value)
        return [value]
    # OBJECT, CNPJ, CPF, EMAIL, etc — pass through. Analyst is responsible
    # for upstream producing the right format.
    return value
