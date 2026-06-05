"""Read-tool da declaração de faturamento homologada (+ analytics).

`get_declaracao_faturamento` é a porta pela qual o agente `revenue_analyst`
recebe o FATO verificável sobre o faturamento: a série mensal homologada
pelo analista, o pacote analítico determinístico (tendência, sazonalidade,
picos/vales, YoY, qualidade) e os sinais de atestação do documento
(assinado? recente? emitente confere?).

Princípio (CLAUDE.md §14 / §19.0 — tool = DADO): a tool NÃO julga. Os
números são calculados deterministicamente em `revenue_analytics` (pura,
auditável) e entregues prontos; o agente raciocina em cima. Hoje a tool lê
o homologado direto do `ai_extraction.extracted_fields` do documento
`revenue_report` (JSONB) — quando a silver canônica de revenue existir, só
o interior desta tool muda; o agente não percebe (a tool é a fronteira de
abstração).
"""

from __future__ import annotations

import json
from typing import Any

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission


@register_tool(
    name="get_declaracao_faturamento",
    description=(
        "Retorna a declaração de faturamento HOMOLOGADA do dossie (série "
        "mensal aprovada pelo analista) já com o pacote analítico "
        "determinístico calculado: agregados, tendência, sazonalidade, "
        "picos/vales (outliers), YoY e qualidade do dado — além dos sinais "
        "de atestação do documento (assinado, idade, emitente confere, "
        "ressalvas). Use estes números como fato; não recalcule. Sua função "
        "é JULGAR o que eles significam (esperado vs anômalo) para o crédito."
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
async def get_declaracao_faturamento(
    scope: ScopedContext, args: dict[str, Any]
) -> str:
    """Lê o faturamento homologado do dossie ativo e devolve série+analytics."""
    from app.modules.credito.services.revenue import build_faturamento_payload

    payload = await build_faturamento_payload(
        scope.db,
        tenant_id=scope.tenant_id,
        dossier_id=scope.extras["dossier_id"],
    )
    return json.dumps(payload, ensure_ascii=False, default=str)
