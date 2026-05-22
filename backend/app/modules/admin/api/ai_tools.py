"""Read-only listing of agent tools (F2.c.4 — CLAUDE.md §19.0).

Tools sao definidas em codigo via `@register_tool` em
`app/agentic/tools/<modulo>/*.py`. Este endpoint apenas EXPÕE a lista
descoberta pelo ToolRegistry — sem CRUD. Editar uma tool exige editar
codigo Python.

Endpoint:
    GET    /api/v1/admin/ia/tools             lista todas as tools registradas

Filtros via query string:
    ?module=credito       so tools com module=Module.CREDITO
    ?cost=cheap           so tools com cost_hint=cheap
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agentic.tools.registry import ToolRegistry
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.system_maintainer_guard import require_system_maintainer
from app.shared.ai.schemas.tool import ToolInfo

router = APIRouter(prefix="/ia/tools", tags=["admin:ia-tools"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


@router.get("", response_model=list[ToolInfo], dependencies=_GUARD)
async def list_tools(
    module: str | None = None,
    cost: str | None = None,
) -> list[ToolInfo]:
    """Lista todas as tools registradas no ToolRegistry global.

    Read-only. Tools sao descobertas no `import app.agentic.tools` (via
    decorators `@register_tool`). Atualizar significa editar codigo +
    deploy.
    """
    all_tools = ToolRegistry.all()

    result: list[ToolInfo] = []
    for t in all_tools:
        if module and t.module.value != module:
            continue
        if cost and t.cost_hint != cost:
            continue
        result.append(
            ToolInfo(
                name=t.name,
                description=t.description,
                module=t.module.value,
                min_permission=t.min_permission.value,
                cost_hint=t.cost_hint,
                input_schema=t.input_schema,
            )
        )

    return result
