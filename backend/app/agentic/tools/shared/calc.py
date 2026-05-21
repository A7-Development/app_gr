"""Tools de calculo determinstico — cross-module.

Tools puras: nao queriam DB, nao precisam de scope.extras. Recebem
ScopedContext por uniformidade (e pro audit poder ler tenant/user
quando precisar logar o calculo), mas o handler so usa os args.

Registradas com `module=Module.SHARED` (a definir no enum) — por ora
uso Module.CREDITO porque sao tools usadas hoje exclusivamente pelo
cross_reference_analyst em workflows de credito. Quando outro modulo
quiser usar, mover pra module=Module.SHARED + atualizar registry.
"""

from __future__ import annotations

import json
from typing import Any

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission


@register_tool(
    name="compare_values",
    description=(
        "Compara dois valores numericos e classifica a divergencia. "
        "Retorna percentual, classificacao ('consistent' < 5%, "
        "'minor_diff' 5-15%, 'major_diff' > 15%) e a diferenca absoluta."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "label_a": {"type": "string", "description": "Label do valor A."},
            "value_a": {"type": "number", "description": "Valor numerico A."},
            "label_b": {"type": "string", "description": "Label do valor B."},
            "value_b": {"type": "number", "description": "Valor numerico B."},
        },
        "required": ["label_a", "value_a", "label_b", "value_b"],
        "additionalProperties": False,
    },
    module=Module.CREDITO,
    min_permission=Permission.READ,
    cost_hint="cheap",
)
async def compare_values(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Compara dois numeros, classifica divergencia. Scope nao usado."""
    _ = scope  # nao usado; aceita por uniformidade de interface

    a = float(args["value_a"])
    b = float(args["value_b"])
    diff = abs(a - b)
    base = max(abs(a), abs(b))
    pct = (diff / base * 100) if base > 0 else 0.0

    if pct < 5:
        classification = "consistent"
    elif pct < 15:
        classification = "minor_diff"
    else:
        classification = "major_diff"

    return json.dumps(
        {
            "label_a": args["label_a"],
            "value_a": a,
            "label_b": args["label_b"],
            "value_b": b,
            "diff_abs": diff,
            "diff_pct": round(pct, 2),
            "classification": classification,
        },
        ensure_ascii=False,
    )


@register_tool(
    name="calculate_metric",
    description=(
        "Calcula um indicador financeiro padrao. Formulas suportadas: "
        "'gross_margin' (gross_profit/revenue), 'ebitda_margin' "
        "(ebitda/revenue), 'current_ratio' (current_assets/current_liab), "
        "'debt_to_equity' (total_liab/equity), 'debt_to_revenue' "
        "(total_debt/revenue). `values` e string JSON com os campos."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "formula": {
                "type": "string",
                "enum": [
                    "gross_margin",
                    "ebitda_margin",
                    "current_ratio",
                    "debt_to_equity",
                    "debt_to_revenue",
                ],
            },
            "values": {
                "type": "string",
                "description": "JSON serializado com os campos necessarios.",
            },
        },
        "required": ["formula", "values"],
        "additionalProperties": False,
    },
    module=Module.CREDITO,
    min_permission=Permission.READ,
    cost_hint="cheap",
)
async def calculate_metric(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Calcula indicador financeiro determinstico. Scope nao usado."""
    _ = scope  # nao usado; aceita por uniformidade de interface

    raw_values = args.get("values")
    if isinstance(raw_values, str):
        try:
            v = json.loads(raw_values)
        except (ValueError, TypeError):
            return "Erro: 'values' deve ser JSON com os campos necessarios."
    elif isinstance(raw_values, dict):
        v = raw_values
    else:
        return "Erro: 'values' deve ser JSON com os campos necessarios."

    formula = args["formula"]
    result: dict[str, Any] = {"formula": formula}

    try:
        if formula == "gross_margin":
            result["value"] = (v["gross_profit"] / v["revenue"]) if v["revenue"] else 0.0
        elif formula == "ebitda_margin":
            result["value"] = (v["ebitda"] / v["revenue"]) if v["revenue"] else 0.0
        elif formula == "current_ratio":
            result["value"] = (
                (v["current_assets"] / v["current_liab"]) if v["current_liab"] else 0.0
            )
        elif formula == "debt_to_equity":
            result["value"] = (v["total_liab"] / v["equity"]) if v["equity"] else 0.0
        elif formula == "debt_to_revenue":
            result["value"] = (v["total_debt"] / v["revenue"]) if v["revenue"] else 0.0
        else:
            result["error"] = f"Formula desconhecida: {formula}"
    except (KeyError, TypeError, ZeroDivisionError) as e:
        result["error"] = str(e)

    return json.dumps(result, ensure_ascii=False)
