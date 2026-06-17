"""Read-tool da consulta Serasa PJ (silver, white-label, ABRANGENTE).

`get_serasa_pj` entrega ao agente a consulta Serasa COMPLETA do silver
(`wh_serasa_pj_*`): score, restricoes, comportamento de pagamento, inquiries,
socios, participacoes, falencias/acoes, suspeita de liminar. Serasa e caro —
a tool extrai o maximo do que ja foi pago. Provider-blind (§13.2.1).
"""

from __future__ import annotations

import json
from typing import Any

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission


@register_tool(
    name="get_serasa_pj",
    description=(
        "Retorna a consulta Serasa PJ COMPLETA da empresa-alvo do dossie: score "
        "H4PJ, cadastrais (faturamento presumido, nº funcionarios, regime), "
        "restricoes (detalhe + resumo por tipo), falencias e acoes judiciais, "
        "comportamento de pagamento (atraso medio mensal, evolucao de "
        "compromissos devidos/vencidos, comparativo vs mercado), demanda por "
        "credito (inquiries mensais = quantas vezes a empresa foi consultada), "
        "socios, participacoes em outras empresas e suspeita de liminar. Dado "
        "oficial caro — use como fato e EXTRAIA o maximo. Sua funcao e JULGAR o "
        "risco de credito: score/restricoes pesam, mas o comportamento de "
        "pagamento (compromissos vencidos) e o pico de inquiries (distress / "
        "shopping de credito) sao sinais fortes. ATENCAO a suspeita_liminar: se "
        "true, os zeros de restricao NAO significam ficha limpa."
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
async def get_serasa_pj(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Lê a consulta Serasa PJ completa da empresa-alvo do silver."""
    from app.modules.credito.services.serasa_dossie import (
        build_serasa_pj_agent_view,
    )

    view = await build_serasa_pj_agent_view(
        scope.db,
        tenant_id=scope.tenant_id,
        dossier_id=scope.extras["dossier_id"],
    )
    if view is None:
        return json.dumps(
            {
                "encontrado": False,
                "mensagem": (
                    "Empresa-alvo nao encontrada no dossie. Sem Serasa para "
                    "analise."
                ),
            },
            ensure_ascii=False,
        )
    return json.dumps(view, ensure_ascii=False, default=str)
