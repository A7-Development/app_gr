"""Read-tool da estrutura societária homologada (contrato social).

`get_contrato_social_estrutura` é a porta pela qual o agente
`social_contract_analyst` recebe o FATO verificável sobre o contrato social:
a ficha homologada pelo analista (CNPJ, razão social, capital, constituição,
objeto, sócios com CPF redactado), a estrutura QSA determinística (soma das
participações, controlador, idade da empresa) e os CRUZAMENTOS com o cadastro
oficial (capital x BDC, razão social x BDC, CNPJ x empresa-alvo, data de
constituição x BDC).

Princípio (§14 / §19.0 — tool = DADO): a tool NÃO julga. Comparações são
calculadas deterministicamente em `services/social_contract.py` (pura,
auditável) e entregues prontas; o agente raciocina em cima. A tool lê o
homologado direto do `ai_extraction.extracted_fields` do documento
`social_contract` — quando a silver canônica societária existir, só o
interior do service muda; o agente não percebe.
"""

from __future__ import annotations

import json
from typing import Any

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission


@register_tool(
    name="get_contrato_social_estrutura",
    description=(
        "Retorna o contrato social HOMOLOGADO do dossiê (ficha aprovada pelo "
        "analista) já com a estrutura societária determinística calculada: "
        "sócios e participações (soma confere?), controlador, idade da "
        "empresa — e os CRUZAMENTOS com o cadastro oficial (CNPJ é o da "
        "empresa-alvo? capital/razão social/data de constituição conferem "
        "com o registro?). Use estes fatos como dados; não recalcule. Sua "
        "função é JULGAR o que significam (poderes de assinatura, alterações "
        "recentes, compatibilidade do objeto, restrições) para o crédito."
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
async def get_contrato_social_estrutura(
    scope: ScopedContext, args: dict[str, Any]
) -> str:
    """Lê o contrato social homologado do dossiê ativo (ficha + cruzamentos)."""
    from app.modules.credito.services.social_contract import (
        build_societario_payload,
    )

    payload = await build_societario_payload(
        scope.db,
        tenant_id=scope.tenant_id,
        dossier_id=scope.extras["dossier_id"],
    )
    return json.dumps(payload, ensure_ascii=False, default=str)
