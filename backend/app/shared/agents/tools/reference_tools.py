"""Cross-reference tools — comparison and metric calculation helpers.

These don't query the DB directly; they receive values from the agent and
return computed comparisons/metrics. Useful for the cross_reference_analyst
to delegate arithmetic to deterministic code (instead of letting the LLM
do math, which is error-prone).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from claude_agent_sdk import tool
from sqlalchemy.ext.asyncio import AsyncSession


def make_reference_tools(
    tenant_id: UUID,
    dossier_id: UUID,
    db: AsyncSession,
) -> list:
    """Build a list of cross-reference tools.

    The (tenant_id, dossier_id, db) closure isn't used by the math helpers
    today, but kept in the factory for consistency and future expansion
    (e.g. comparing against historical benchmarks for the same tenant).
    """
    _ = (tenant_id, dossier_id, db)  # silence linter, future-use placeholder

    @tool(
        "compare_values",
        "Compara dois valores numericos e classifica a divergencia. "
        "Retorna percentual, classificacao ('consistent' < 5%, 'minor_diff' "
        "5-15%, 'major_diff' > 15%) e o valor absoluto da diferenca.",
        {"label_a": str, "value_a": float, "label_b": str, "value_b": float},
    )
    async def compare_values(args: dict[str, Any]) -> dict[str, Any]:
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

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
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
                    ),
                }
            ]
        }

    @tool(
        "calculate_metric",
        "Calcula um indicador financeiro padrao. Formulas suportadas: "
        "'gross_margin' (gross_profit/revenue), 'ebitda_margin' "
        "(ebitda/revenue), 'current_ratio' (current_assets/current_liab), "
        "'debt_to_equity' (total_liab/equity), 'debt_to_revenue' "
        "(total_debt/revenue).",
        {"formula": str, "values": str},
    )
    async def calculate_metric(args: dict[str, Any]) -> dict[str, Any]:
        try:
            v = json.loads(args["values"])
        except (ValueError, TypeError):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Erro: 'values' deve ser JSON com os campos necessarios.",
                    }
                ]
            }

        formula = args["formula"]
        result: dict[str, Any] = {"formula": formula}

        try:
            if formula == "gross_margin":
                result["value"] = (v["gross_profit"] / v["revenue"]) if v["revenue"] else 0.0
            elif formula == "ebitda_margin":
                result["value"] = (v["ebitda"] / v["revenue"]) if v["revenue"] else 0.0
            elif formula == "current_ratio":
                result["value"] = (v["current_assets"] / v["current_liab"]) if v["current_liab"] else 0.0
            elif formula == "debt_to_equity":
                result["value"] = (v["total_liab"] / v["equity"]) if v["equity"] else 0.0
            elif formula == "debt_to_revenue":
                result["value"] = (v["total_debt"] / v["revenue"]) if v["revenue"] else 0.0
            else:
                result["error"] = f"Formula desconhecida: {formula}"
        except (KeyError, TypeError, ZeroDivisionError) as e:
            result["error"] = str(e)

        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}

    return [compare_values, calculate_metric]
