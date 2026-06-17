"""Read-tool do quadro societario da empresa-alvo (silver, white-label).

`get_quadro_societario` entrega ao agente o controle atual + churn + risco do
grupo economico, lido do silver canonico (`wh_pj_vinculo` +
`wh_pj_grupo_indicador`) — provider-blind (§13.2.1). Populado pelo node BDC.
"""

from __future__ import annotations

import json
from typing import Any

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission


@register_tool(
    name="get_quadro_societario",
    description=(
        "Retorna o quadro societario da empresa-alvo do dossie: controle atual "
        "(socios/quotistas ativos com papel e data de entrada), mudancas "
        "recentes de controle (saidas/entradas = churn) e indicadores do grupo "
        "economico de 1o nivel (empresas, ativas, sancionados, PEPs, processos). "
        "Dado oficial — use como fato. Sua funcao e JULGAR a estrutura de "
        "controle para o credito: o controle e estavel ou ha rotatividade "
        "recente? ha concentracao ou partes relacionadas? o grupo tem sancao ou "
        "litigio em volume relevante? Cada bloco traz a idade da informacao."
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
async def get_quadro_societario(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Lê o quadro societario da empresa-alvo do silver."""
    from app.modules.credito.services.bdc_dossie import (
        build_quadro_societario_agent_view,
    )

    view = await build_quadro_societario_agent_view(
        scope.db,
        tenant_id=scope.tenant_id,
        dossier_id=scope.extras["dossier_id"],
    )
    if view is None:
        return json.dumps(
            {
                "encontrado": False,
                "mensagem": (
                    "Empresa-alvo nao encontrada no dossie. Sem quadro "
                    "societario para analise."
                ),
            },
            ensure_ascii=False,
        )
    return json.dumps(view, ensure_ascii=False, default=str)
