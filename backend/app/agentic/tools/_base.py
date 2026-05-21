"""AgentTool + @register_tool decorator (CLAUDE.md §19.0).

A tool e uma funcao atomica que o agente IA pode invocar — query SQL
pre-produzida, calculo, equacao regulatoria, API externa, MCP, gerador
de relatorio. Registrada via decorator, descoberta dinamicamente em
runtime pelo `ToolRegistry`.

Interface canonica:

```python
@register_tool(
    name="read_dossier_section",
    description="Le secao do dossie atual.",
    input_schema={...},  # JSON Schema do payload aceito do LLM
    module=Module.CREDITO,
    min_permission=Permission.READ,
    cost_hint="cheap",
)
async def read_dossier_section(scope: ScopedContext, args: dict) -> str:
    # scope.tenant_id, scope.empresa_id, scope.db, scope.extras["dossier_id"]
    # nunca lidos de args (LLM nao mente sobre scope)
    ...
```

Tool e identificada por `name` (visivel ao LLM) + `module` (tag pra
filtragem). Names devem ser unicos no registry — colisao = erro de
arranjo.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from app.agentic._scope import ScopedContext
from app.core.enums import Module, Permission

# Handler signature: (scope, args_dict) -> awaitable str.
# Args_dict e parsed do tool_use.input do LLM.
ToolHandler = Callable[[ScopedContext, dict[str, Any]], Awaitable[str]]

CostHint = Literal["cheap", "medium", "expensive"]


@dataclass(frozen=True, slots=True)
class AgentTool:
    """Uma tool callable pelo agente.

    Frozen porque deve ser tratada como imutavel apos registro. Para
    "customizar" uma tool (ex.: tenant-specific override), registre uma
    nova com nome distinto, nao mute a existente.

    Attributes:
        name: nome unico visivel ao LLM (vai em `tool_use.name`). NAO
            inclui prefixo de modulo — modulo e metadado separado.
        description: linguagem natural pro modelo decidir quando usar.
        input_schema: JSON Schema do payload aceito (objeto, com
            type/properties/required).
        handler: coroutine `(scope, args_dict) -> str`. Erros viram
            mensagem de erro pro modelo via runtime.
        module: tag de modulo. Registry filtra por isso.
        min_permission: permissao minima no `module` requerida do user
            que invoca o agente.
        cost_hint: indicacao de custo pro modelo priorizar tools baratas.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    module: Module
    min_permission: Permission
    cost_hint: CostHint = "cheap"

    def to_api_definition(self) -> dict[str, Any]:
        """Shape esperado por `messages.create(tools=[...])` do Anthropic."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def register_tool(
    *,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    module: Module,
    min_permission: Permission = Permission.READ,
    cost_hint: CostHint = "cheap",
) -> Callable[[ToolHandler], ToolHandler]:
    """Decorator que registra uma tool no ToolRegistry global.

    Uso:

        @register_tool(
            name="read_dossier_section",
            description="...",
            input_schema={...},
            module=Module.CREDITO,
            min_permission=Permission.READ,
            cost_hint="cheap",
        )
        async def read_dossier_section(scope: ScopedContext, args: dict) -> str:
            ...

    O handler decorado e devolvido inalterado — voce pode chama-lo direto
    em testes unitarios sem precisar do registry. O efeito colateral e
    apenas registrar a tool no `ToolRegistry` na importacao do modulo.
    """
    # Import tardio pra evitar circular import:
    # _base.py -> registry.py -> _base.py.
    from app.agentic.tools.registry import ToolRegistry

    def decorator(handler: ToolHandler) -> ToolHandler:
        tool = AgentTool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
            module=module,
            min_permission=min_permission,
            cost_hint=cost_hint,
        )
        ToolRegistry.register(tool)
        return handler

    return decorator


def string_schema(*fields: str) -> dict[str, Any]:
    """Helper: schema 'objeto com N campos string obrigatorios'."""
    return {
        "type": "object",
        "properties": {f: {"type": "string"} for f in fields},
        "required": list(fields),
        "additionalProperties": False,
    }
