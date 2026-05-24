"""Memory tools (opcionais) — remember/recall fechadas sobre uma session.

Estas tools NAO sao registradas no `ToolRegistry` global. Sao parte da
infra de memoria (CLAUDE.md sec 19.11 D4 hybrid):

    scratchpad           bloco textual auto-injetado no prompt (default)
    remember / recall    tools opcionais quando precisa estrutura

Sao fechadas sobre uma `AnalysisSession` viva (closure sobre `kv_store`).
O runtime injeta o par {remember, recall} quando `spec.enable_memory_tools`
e True E ha session ativa — caso contrario, agente nao ve essas tools.

Diferente das tools de dominio (que recebem ScopedContext + consultam
DB), memory tools operam sobre a session in-memory. Por isso nao usam
`@register_tool` — closure sobre session torna o factory mais natural
que injetar via registry.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from app.agentic.tools._base import AgentTool
from app.core.enums import Module, Permission

if TYPE_CHECKING:
    from app.agentic._scope import ScopedContext
    from app.agentic.memory._base import AnalysisSession


_REMEMBER_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "key": {
            "type": "string",
            "description": (
                "Identificador da informacao a guardar (ex.: "
                "'cedente_a_score', 'ebitda_target'). Use snake_case."
            ),
        },
        "value": {
            "description": (
                "Valor a guardar. Aceita string, number, boolean, "
                "list ou object."
            ),
        },
    },
    "required": ["key", "value"],
    "additionalProperties": False,
}

_RECALL_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "key": {
            "type": "string",
            "description": "Identificador previamente salvo via 'remember'.",
        },
    },
    "required": ["key"],
    "additionalProperties": False,
}


def make_memory_tools(session: AnalysisSession) -> list[AgentTool]:
    """Devolve {remember, recall} fechadas sobre `session.kv_store`.

    Use no runtime quando `spec.enable_memory_tools=True` e ha session
    ativa. Tools sao no-cache, no-write-to-DB — manipulam apenas o
    `kv_store` in-memory da session.
    """

    async def _remember(scope: ScopedContext, args: dict[str, Any]) -> str:
        _ = scope  # nao usado; sessao isolada por construcao
        key = str(args.get("key", "")).strip()
        if not key:
            return "Erro: 'key' nao pode ser vazio."
        value = args.get("value")
        session.kv_store[key] = value
        # Registra trace human-readable. Conteudo cru fica em kv_store.
        try:
            preview = json.dumps(value, ensure_ascii=False, default=str)[:200]
        except (TypeError, ValueError):
            preview = str(value)[:200]
        return f"OK. Guardado '{key}' = {preview}"

    async def _recall(scope: ScopedContext, args: dict[str, Any]) -> str:
        _ = scope
        key = str(args.get("key", "")).strip()
        if not key:
            return "Erro: 'key' nao pode ser vazio."
        if key not in session.kv_store:
            return f"(nada guardado em '{key}')"
        value = session.kv_store[key]
        try:
            return json.dumps({key: value}, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return f"{key} = {value!s}"

    remember_tool = AgentTool(
        name="remember",
        description=(
            "Guarda um valor estruturado na memoria desta analise. Use "
            "quando precisar de uma informacao depois (em outro turn ou "
            "outro agente da mesma sessao). O valor sobrevive enquanto "
            "a sessao estiver viva."
        ),
        input_schema=_REMEMBER_INPUT_SCHEMA,
        handler=_remember,
        module=Module.ADMIN,
        min_permission=Permission.READ,
        cost_hint="cheap",
        cacheable=False,
    )

    recall_tool = AgentTool(
        name="recall",
        description=(
            "Recupera um valor previamente guardado via 'remember' nesta "
            "analise. Retorna '(nada guardado em <key>)' quando a chave "
            "nao foi setada."
        ),
        input_schema=_RECALL_INPUT_SCHEMA,
        handler=_recall,
        module=Module.ADMIN,
        min_permission=Permission.READ,
        cost_hint="cheap",
        cacheable=False,
    )

    return [remember_tool, recall_tool]
