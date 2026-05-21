"""Camada de tools agenticas (CLAUDE.md §19.0).

Estrutura:
    _scope.py       ScopedContext (em app/agentic/_scope.py)
    _base.py        AgentTool + @register_tool decorator + string_schema
    registry.py     ToolRegistry singleton

Subdirs por modulo (dominio):
    credito/        dossier, document (3 + 2 tools)
    shared/         calc (2 tools)

Importar subdirs aqui forca execucao dos decorators na carga do pacote
— sem isso, tools nao "aparecem" no registry ate alguem importar o
modulo delas, gerando flakiness.
"""

from app.agentic.tools import credito, shared  # noqa: F401
from app.agentic.tools._base import AgentTool, register_tool, string_schema
from app.agentic.tools.registry import ToolRegistry

__all__ = [
    "AgentTool",
    "ToolRegistry",
    "register_tool",
    "string_schema",
]
