"""AgentTool — interface canonica de uma ferramenta exposta ao agente IA.

Substitui o decorator `@tool` de `claude-agent-sdk` desde 2026-05-02 quando
o runtime migrou do CLI subprocess para a Anthropic Messages API direta
(via SDK oficial `anthropic`).

Cada `make_<group>_tools()` em `tools/*.py` retorna uma lista de
`AgentTool`. O runtime monta a `tools[]` que vai pro Messages API a partir
de `to_api_definition()`, e mantem um dict `name -> handler` pra dispatch
quando o modelo retorna `tool_use` blocks.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentTool:
    """Uma tool callable pelo agente.

    Attributes:
        name: nome unico (vai como `tool_use.name` no API).
        description: descricao em linguagem natural pra o modelo decidir
            quando usar.
        input_schema: JSON Schema do payload aceito (objeto, com
            `type/properties/required`).
        handler: coroutine que recebe `dict` (= `tool_use.input`) e devolve
            texto puro pra `tool_result.content`. Excecoes sao capturadas
            pelo runtime e viradas em mensagens de erro pro modelo.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[str]]

    def to_api_definition(self) -> dict[str, Any]:
        """Shape esperado por `messages.create(tools=[...])`."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def string_schema(*fields: str) -> dict[str, Any]:
    """Helper rapido pra schema 'objeto com N campos string obrigatorios'.

    Maioria das tools so precisa disso — viver da nuance no JSON Schema
    nao paga.
    """
    return {
        "type": "object",
        "properties": {f: {"type": "string"} for f in fields},
        "required": list(fields),
        "additionalProperties": False,
    }
