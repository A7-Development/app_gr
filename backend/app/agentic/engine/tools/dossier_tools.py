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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.engine.tools._base import AgentTool


def make_dossier_tools(
    tenant_id: UUID,
    dossier_id: UUID,
    db: AsyncSession,
) -> list[AgentTool]:
    """Build a list of AgentTool instances scoped to the given tenant + dossier."""

    async def _read_dossier_section(args: dict[str, Any]) -> str:
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
            return f"Nenhum dado salvo na secao '{section}' ainda."
        payload = [{"section": r.section, "data": r.ai_analysis} for r in rows]
        return json.dumps(payload, ensure_ascii=False)

    async def _flag_red_flag(args: dict[str, Any]) -> str:
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
        return f"Red flag registrada: {flag.id}"

    async def _save_analysis(args: dict[str, Any]) -> str:
        from app.modules.credito.models.analysis import CreditDossierAnalysis

        # `indicators` chega como string JSON serializada (tools de string
        # sao mais simples pra o modelo). Aceitamos tambem objeto cru caso
        # algum modelo decida passar o objeto direto.
        raw_indicators = args.get("indicators")
        if isinstance(raw_indicators, str):
            try:
                indicators = json.loads(raw_indicators)
            except (ValueError, TypeError):
                indicators = {"raw": raw_indicators}
        elif isinstance(raw_indicators, dict):
            indicators = raw_indicators
        else:
            indicators = {}

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
        return f"Analise salva (secao '{args['section']}')."

    return [
        AgentTool(
            name="read_dossier_section",
            description=(
                "Le dados estruturados de uma secao do dossie. Use para acessar "
                "dados ja coletados por outros nos do workflow. Secoes validas: "
                "'plea', 'identification', 'bureau_queries', 'financial', 'indebtedness', "
                "'legal', 'partners', 'commercial_visit', 'documents', 'cross_reference'."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "description": "Nome da secao (ex.: 'financial').",
                    }
                },
                "required": ["section"],
                "additionalProperties": False,
            },
            handler=_read_dossier_section,
        ),
        AgentTool(
            name="flag_red_flag",
            description=(
                "Registra um red flag identificado durante a analise. Severity "
                "deve ser 'critical', 'important' ou 'informational'. Cite a "
                "evidencia (qual documento, fonte ou achado motivou o flag)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "important", "informational"],
                        "description": "Gravidade do achado.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Titulo curto (max 200 chars).",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detalhamento do problema.",
                    },
                    "evidence": {
                        "type": "string",
                        "description": "Fonte ou trecho que motivou o flag.",
                    },
                },
                "required": ["severity", "title", "description", "evidence"],
                "additionalProperties": False,
            },
            handler=_flag_red_flag,
        ),
        AgentTool(
            name="save_analysis",
            description=(
                "Salva o resumo estruturado de uma analise de secao. Use ao "
                "final do raciocinio para persistir summary + indicadores "
                "principais. `indicators` deve ser uma string JSON com os "
                "valores numericos relevantes."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "description": "Secao analisada.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Resumo executivo da analise.",
                    },
                    "indicators": {
                        "type": "string",
                        "description": "JSON serializado com indicadores numericos.",
                    },
                },
                "required": ["section", "summary", "indicators"],
                "additionalProperties": False,
            },
            handler=_save_analysis,
        ),
    ]
