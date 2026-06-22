"""Read-tool de protestos (CENPROT/IEPTB via Infosimples), silver-first.

`get_protestos` entrega ao agente a ultima consulta de protesto da empresa-alvo
do dossie (`wh_protesto_*`): existencia, qtd, valor total e os titulos por
cartorio -- com credor (cedente/apresentante) onde a fonte identificar (detalhe
SP). Provider-blind (§13.2.1). Le do silver; quem dispara a consulta paga e o
endpoint/playbook, nao a tool.
"""

from __future__ import annotations

import json
from typing import Any

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission


@register_tool(
    name="get_protestos",
    description=(
        "Retorna a ultima consulta de PROTESTOS (cartorio) da empresa-alvo do "
        "dossie: se constam protestos, quantidade, valor total e a lista de "
        "titulos protestados (cartorio, cidade, UF, valor). A fonte padrao "
        "(CENPROT-SP) tambem traz, por titulo, os VALORES de cancelamento e "
        "quitacao (custo p/ cancelar/quitar o protesto — NAO sao status: pode "
        "estar ABERTO mesmo com esses valores preenchidos). `completo`=false: a fonte so "
        "devolveu a 1a pagina (lista parcial). O CREDOR (cedente/apresentante) so "
        "vem na fonte IEPTB (detalhe SP); credor=null = fonte nao identificou, "
        "NAO 'sem credor'. Protesto e divida levada a cartorio por falta de "
        "pagamento: sinal forte de risco. Use como fato e PESE — varios protestos "
        "abertos ou de valor alto indicam distress."
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
async def get_protestos(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Le do silver a ultima consulta de protesto da empresa-alvo do dossie."""
    from app.modules.credito.services.protesto_dossie import (
        build_protesto_agent_view,
    )

    view = await build_protesto_agent_view(
        scope.db,
        tenant_id=scope.tenant_id,
        dossier_id=scope.extras["dossier_id"],
    )
    if view is None:
        return json.dumps(
            {
                "encontrado": False,
                "mensagem": (
                    "Empresa-alvo nao encontrada no dossie. Sem protestos para "
                    "analise."
                ),
            },
            ensure_ascii=False,
        )
    return json.dumps(view, ensure_ascii=False, default=str)
