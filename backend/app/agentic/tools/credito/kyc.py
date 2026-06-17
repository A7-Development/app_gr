"""Read-tool do KYC da empresa-alvo + socios (silver, white-label).

`get_kyc_pj` entrega flags de PEP/sancao por sujeito + ocorrencias COM nivel de
confianca (match_rate), lido do silver canonico (`wh_pj_kyc` +
`wh_pj_kyc_ocorrencia`). O bureau casa por NOME — a tool separa alta de baixa
confianca pro agente nao tratar homonimo como sancao. Provider-blind (§13.2.1).
"""

from __future__ import annotations

import json
from typing import Any

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission


@register_tool(
    name="get_kyc_pj",
    description=(
        "Retorna o KYC/compliance da empresa-alvo e de seus socios: flags de PEP "
        "e sancao por sujeito + lista de ocorrencias. ATENCAO ao match_rate: o "
        "bureau casa sancoes por NOME, entao achados de BAIXA confianca sao "
        "provavel homonimo (vem so contados, nao como sancao). Use 'ocorrencias "
        "_confirmadas' (alta confianca) como fato; trate baixa confianca como "
        "sinal a investigar, nao como veredito. Sua funcao e JULGAR: ha sancao "
        "ou PEP de ALTA confianca em socio de controle? quao recente e o achado "
        "(atualizado_em)?"
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
async def get_kyc_pj(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Lê o KYC da empresa-alvo + socios do silver (com threshold de match)."""
    from app.modules.credito.services.bdc_dossie import build_kyc_agent_view

    view = await build_kyc_agent_view(
        scope.db,
        tenant_id=scope.tenant_id,
        dossier_id=scope.extras["dossier_id"],
    )
    if view is None:
        return json.dumps(
            {
                "encontrado": False,
                "mensagem": (
                    "Empresa-alvo nao encontrada no dossie. Sem KYC para analise."
                ),
            },
            ensure_ascii=False,
        )
    return json.dumps(view, ensure_ascii=False, default=str)
