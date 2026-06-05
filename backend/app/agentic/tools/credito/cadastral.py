"""Read-tool dos dados cadastrais homologados/coletados (silver, white-label).

`get_dados_cadastrais` é a porta pela qual o agente `cadastral_analyst`
recebe os dados cadastrais da empresa-alvo (situação, CNAE, capital,
fundação, regime) já normalizados a partir do silver canônico — provider-
blind por construção (§13.2.1 + white-label). Mesma fonte do card da tela
(`GET /dossies/{id}/cadastral`).
"""

from __future__ import annotations

import json
from typing import Any

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission


@register_tool(
    name="get_dados_cadastrais",
    description=(
        "Retorna os dados cadastrais da empresa-alvo do dossie já coletados de "
        "fonte oficial (situação cadastral, CNAE principal e secundárias, "
        "capital social, data de fundação, regime tributário, natureza "
        "jurídica, porte). Dado oficial — use como fato. Sua função é JULGAR a "
        "saúde cadastral para o crédito (situação ativa? tempo de atividade? "
        "CNAE compatível com a operação? capital coerente com o porte?)."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    module=Module.CREDITO,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_dados_cadastrais(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Lê a silver cadastral da empresa-alvo do dossie ativo (white-label)."""
    from app.modules.credito.services.cadastral import load_cadastral_silver_view

    view = await load_cadastral_silver_view(
        scope.db,
        tenant_id=scope.tenant_id,
        dossier_id=scope.extras["dossier_id"],
    )
    if view is None:
        return json.dumps(
            {
                "encontrado": False,
                "mensagem": (
                    "Empresa-alvo não encontrada no dossie. Sem dados "
                    "cadastrais para análise."
                ),
            },
            ensure_ascii=False,
        )
    return json.dumps(view, ensure_ascii=False, default=str)
