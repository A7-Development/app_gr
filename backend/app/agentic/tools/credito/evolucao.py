"""Read-tool da evolucao temporal da empresa-alvo (silver, white-label).

`get_evolucao_pj` entrega ao agente o porte ATUAL + a trajetoria da empresa:
funcionarios (corrente + serie mensal), tendencia de crescimento (YoY 1a/3a/5a),
faixa de faturamento ao longo do tempo, socios e nivel de atividade. Lido do
silver canonico (`wh_pj_evolucao` + `wh_pj_evolucao_mensal`) — provider-blind
(§13.2.1). Populado pelo node BDC (dataset company_evolution).
"""

from __future__ import annotations

import json
from typing import Any

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission


@register_tool(
    name="get_evolucao_pj",
    description=(
        "Retorna a evolucao temporal da empresa-alvo do dossie: numero de "
        "funcionarios ATUAL (headcount corrente, nao acumulado) + serie mensal, "
        "tendencia de crescimento ano-a-ano (1a/3a/5a: GROW UP / STABLE / "
        "SHRINK), faixa de faturamento atual e ao longo do tempo, evolucao do "
        "quadro de socios e do nivel de atividade, e flag de mudanca de QSA. "
        "Dado oficial — use como fato. Sua funcao e JULGAR a trajetoria para o "
        "credito: a empresa cresce, estabilizou ou encolhe? o porte (funcionarios"
        "/faturamento) e coerente com a operacao pretendida? houve contracao "
        "recente ou troca de controle? A serie mensal e a curva — use pra ver a "
        "tendencia, nao so o ponto atual."
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
async def get_evolucao_pj(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Lê a evolucao temporal da empresa-alvo do silver."""
    from app.modules.credito.services.bdc_dossie import build_evolucao_agent_view

    view = await build_evolucao_agent_view(
        scope.db,
        tenant_id=scope.tenant_id,
        dossier_id=scope.extras["dossier_id"],
    )
    if view is None:
        return json.dumps(
            {
                "encontrado": False,
                "mensagem": (
                    "Empresa-alvo nao encontrada no dossie. Sem evolucao "
                    "temporal para analise."
                ),
            },
            ensure_ascii=False,
        )
    return json.dumps(view, ensure_ascii=False, default=str)
