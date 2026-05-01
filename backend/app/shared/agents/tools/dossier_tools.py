"""Dossier tools — agent-callable functions over the dossier data.

These tools are tenant-scoped: the factory captures `tenant_id` and
`dossier_id`, and every implementation queries with those constraints.
The agent CANNOT pass arbitrary IDs.

Tools created here:
- read_dossier_section(section)  — fetch structured data of a section
- flag_red_flag(severity, title, description, evidence)
- save_analysis(section, summary, indicators)
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from claude_agent_sdk import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def make_dossier_tools(
    tenant_id: UUID,
    dossier_id: UUID,
    db: AsyncSession,
) -> list:
    """Build a list of tool callables scoped to the given tenant + dossier."""

    @tool(
        "read_dossier_section",
        "Le dados estruturados de uma secao do dossie. Use para acessar "
        "dados ja coletados por outros nos do workflow. Secoes validas: "
        "'plea', 'identification', 'bureau_queries', 'financial', 'indebtedness', "
        "'legal', 'partners', 'commercial_visit', 'documents', 'cross_reference'.",
        {"section": str},
    )
    async def read_dossier_section(args: dict[str, Any]) -> dict[str, Any]:
        section = args["section"]
        # Late import to avoid circular reference.
        from app.modules.credito.models.analysis import CreditDossierAnalysis

        rows = (
            await db.execute(
                select(CreditDossierAnalysis).where(
                    CreditDossierAnalysis.tenant_id == tenant_id,
                    CreditDossierAnalysis.dossier_id == dossier_id,
                    CreditDossierAnalysis.section == section,
                )
            )
        ).scalars().all()
        if not rows:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Nenhum dado salvo na secao '{section}' ainda.",
                    }
                ]
            }
        payload = [{"section": r.section, "data": r.ai_analysis} for r in rows]
        return {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]
        }

    @tool(
        "flag_red_flag",
        "Registra um red flag identificado durante a analise. Severity deve ser "
        "'critical', 'important' ou 'informational'. Cite a evidencia (qual "
        "documento, fonte ou achado motivou o flag).",
        {"severity": str, "title": str, "description": str, "evidence": str},
    )
    async def flag_red_flag(args: dict[str, Any]) -> dict[str, Any]:
        from app.modules.credito.models.red_flag import CreditDossierRedFlag

        flag = CreditDossierRedFlag(
            tenant_id=tenant_id,
            dossier_id=dossier_id,
            severity=args["severity"],
            title=args["title"][:200],
            description=args["description"],
            evidence=args["evidence"],
        )
        db.add(flag)
        await db.flush()
        return {
            "content": [
                {"type": "text", "text": f"Red flag registrada: {flag.id}"}
            ]
        }

    @tool(
        "save_analysis",
        "Salva o resumo estruturado de uma analise de secao. Use ao final "
        "do raciocinio para persistir summary + indicadores principais.",
        {"section": str, "summary": str, "indicators": str},
    )
    async def save_analysis(args: dict[str, Any]) -> dict[str, Any]:
        from app.modules.credito.models.analysis import CreditDossierAnalysis

        try:
            indicators = json.loads(args["indicators"])
        except (ValueError, TypeError):
            indicators = {"raw": args["indicators"]}

        analysis = CreditDossierAnalysis(
            tenant_id=tenant_id,
            dossier_id=dossier_id,
            section=args["section"],
            ai_analysis={
                "summary": args["summary"],
                "indicators": indicators,
            },
        )
        db.add(analysis)
        await db.flush()
        return {
            "content": [
                {"type": "text", "text": f"Analise salva (secao '{args['section']}')."}
            ]
        }

    return [read_dossier_section, flag_red_flag, save_analysis]
