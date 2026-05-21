"""Tools de leitura/escrita do dossie de credito.

Tools registradas:
- read_dossier_section(section) — fetch dados de uma secao
- flag_red_flag(severity, title, description, evidence)
- save_analysis(section, summary, indicators)

Antes (F0): factory `make_dossier_tools(tenant_id, dossier_id, db)` com
closure. Apos F2.a: tools recebem `ScopedContext` em runtime. dossier_id
viaja em `scope.extras["dossier_id"]` (preenchido pelo invocador, nao
pelo LLM).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission


@register_tool(
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
    module=Module.CREDITO,
    min_permission=Permission.READ,
    cost_hint="cheap",
)
async def read_dossier_section(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Le dados de uma secao do dossie ativo (scope.extras['dossier_id'])."""
    from app.modules.credito.models.analysis import CreditDossierAnalysis

    section = args["section"]
    dossier_id = scope.extras["dossier_id"]

    rows = (
        await scope.db.execute(
            select(CreditDossierAnalysis).where(
                CreditDossierAnalysis.tenant_id == scope.tenant_id,
                CreditDossierAnalysis.dossier_id == dossier_id,
                CreditDossierAnalysis.section == section,
            )
        )
    ).scalars().all()
    if not rows:
        return f"Nenhum dado salvo na secao '{section}' ainda."
    payload = [{"section": r.section, "data": r.ai_analysis} for r in rows]
    return json.dumps(payload, ensure_ascii=False)


@register_tool(
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
    module=Module.CREDITO,
    min_permission=Permission.WRITE,
    cost_hint="cheap",
)
async def flag_red_flag(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Registra red flag no dossie ativo (scope.extras['dossier_id'])."""
    from app.modules.credito.models.red_flag import CreditDossierRedFlag

    dossier_id = scope.extras["dossier_id"]

    flag = CreditDossierRedFlag(
        tenant_id=scope.tenant_id,
        dossier_id=dossier_id,
        severity=args["severity"],
        title=args["title"][:200],
        description=args["description"],
        evidence=args["evidence"],
    )
    scope.db.add(flag)
    await scope.db.flush()
    return f"Red flag registrada: {flag.id}"


@register_tool(
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
    module=Module.CREDITO,
    min_permission=Permission.WRITE,
    cost_hint="cheap",
)
async def save_analysis(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Persiste analise de secao no dossie ativo (scope.extras['dossier_id'])."""
    from app.modules.credito.models.analysis import CreditDossierAnalysis

    dossier_id = scope.extras["dossier_id"]

    # `indicators` chega como string JSON serializada (tools de string sao
    # mais simples pra o modelo). Aceitamos tambem objeto cru caso algum
    # modelo decida passar o objeto direto.
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
        tenant_id=scope.tenant_id,
        dossier_id=dossier_id,
        section=args["section"],
        ai_analysis={
            "summary": args["summary"],
            "indicators": indicators,
        },
    )
    scope.db.add(analysis)
    await scope.db.flush()
    return f"Analise salva (secao '{args['section']}')."
