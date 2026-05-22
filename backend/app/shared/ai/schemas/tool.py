"""Pydantic schemas (DTOs) para endpoints de /admin/ia/tools.

Tools sao definidas em codigo via `@register_tool` (CLAUDE.md §19.0). UI
e somente leitura — para mudar tool, edita o arquivo Python correspondente
em `app/agentic/tools/<modulo>/`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolInfo(BaseModel):
    """Resumo de uma tool registrada via decorator."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    module: str
    min_permission: str  # "none" | "read" | "write" | "admin"
    cost_hint: str  # "cheap" | "medium" | "expensive"
    input_schema: dict[str, Any]
