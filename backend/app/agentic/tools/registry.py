"""ToolRegistry — descoberta dinamica de tools por scope (CLAUDE.md §19.0).

Tools registradas via `@register_tool` em modulos individuais. Registry
e singleton global. Em runtime, `ToolRegistry.get_available(scope)`
retorna a lista filtrada por:

1. Modulo do scope (tool.module == scope.module OR tool em shared)
2. Permissao do user (scope.permissions[tool.module] >= tool.min_permission)
3. Pattern `allowed` (subset opcional declarado pelo agente)

Pattern de import:
    `app/agentic/tools/__init__.py` importa explicitamente todos os
    subdirs (`credito`, `shared`, etc) pra forcar execucao dos decorators.
    Sem isso, tools nao "aparecem" no registry ate alguem importar o
    modulo delas — flakiness em testes.
"""

from __future__ import annotations

import fnmatch
import logging
from threading import RLock

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import AgentTool
from app.core.enums import Module

logger = logging.getLogger(__name__)


class _ToolRegistry:
    """Singleton registry. Use via `ToolRegistry` (alias do modulo)."""

    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}
        self._lock = RLock()

    def register(self, tool: AgentTool) -> None:
        """Registra uma tool. Colisao de nome = erro de arranjo."""
        with self._lock:
            if tool.name in self._tools:
                existing = self._tools[tool.name]
                if existing is tool:
                    # Re-import do mesmo modulo durante testes: silencioso.
                    return
                raise ValueError(
                    f"Tool name collision: '{tool.name}' ja registrada "
                    f"(modulo={existing.module.value}). Nova tentativa em "
                    f"modulo={tool.module.value}. Nomes devem ser unicos."
                )
            self._tools[tool.name] = tool
            logger.debug(
                "Tool registered: name=%s module=%s min_perm=%s cost=%s",
                tool.name,
                tool.module.value,
                tool.min_permission.value,
                tool.cost_hint,
            )

    def get(self, name: str) -> AgentTool | None:
        """Lookup direto por nome. None se nao registrada."""
        return self._tools.get(name)

    def all(self) -> list[AgentTool]:
        """Lista todas as tools registradas (ordenada por nome)."""
        return sorted(self._tools.values(), key=lambda t: t.name)

    def get_available(
        self,
        scope: ScopedContext,
        allowed: list[str] | None = None,
        *,
        cross_module: bool = False,
    ) -> list[AgentTool]:
        """Retorna tools disponiveis pro scope, filtradas.

        Filtros aplicados em ordem:

        1. **Modulo**: tool.module == scope.module OR tool em modulo
           generico (sem modulo proprio). Se `cross_module=True`, libera
           tools de qualquer modulo (usado por agentes que tem
           cross_module=true explicitamente).
        2. **Permissao**: user precisa ter no minimo
           `tool.min_permission` no `tool.module`.
        3. **Allowed pattern (opcional)**: subset que o agente declara
           via `AgentDefinition.allowed_tools`. Suporta nome literal
           (`"read_dossier_section"`) ou wildcard (`"credito.*"` =
           todas do modulo Credito).
        """
        result: list[AgentTool] = []
        for tool in self._tools.values():
            # 1. Modulo
            if not cross_module and tool.module != scope.module:
                # Tools de SHARED (futuro Module.SHARED?) precisariam de
                # tratamento aqui. Hoje todas as tools tem modulo
                # concreto; "shared" e organizacao de pasta, nao um
                # modulo do enum.
                continue

            # 2. Permissao
            if not scope.has_permission(tool.module, tool.min_permission):
                continue

            # 3. Allowed pattern
            if allowed is not None and not _matches_any(tool, allowed):
                continue

            result.append(tool)

        return sorted(result, key=lambda t: t.name)

    def get_available_multimodule(
        self,
        scope: ScopedContext,
        allowed: list[str] | None = None,
    ) -> list[AgentTool]:
        """Cardapio HOLISTICO (Copiloto — spec copiloto-mcp §6.3).

        Ignora o modulo unico do scope: entram tools de TODOS os modulos
        em que o usuario tem permissao (`scope.permissions` ja consolida
        permissao do user ∩ assinatura do tenant). Capability de modulo
        sem permissao NAO entra — vazamento de modulo e eval com
        tolerancia zero (§14.2).
        """
        result: list[AgentTool] = []
        for tool in self._tools.values():
            if not scope.has_permission(tool.module, tool.min_permission):
                continue
            if allowed is not None and not _matches_any(tool, allowed):
                continue
            result.append(tool)
        return sorted(result, key=lambda t: t.name)

    def clear_for_testing(self) -> None:
        """SO usar em testes. Limpa o registry pra setup isolado."""
        with self._lock:
            self._tools.clear()


def _matches_any(tool: AgentTool, patterns: list[str]) -> bool:
    """True se a tool casa com pelo menos um pattern.

    Patterns aceitos:
    - `"read_dossier_section"` — match literal por nome
    - `"credito.*"` — match por modulo (todas as tools de Credito)
    - `"*"` — match qualquer
    """
    for pattern in patterns:
        # Wildcard de modulo: "credito.*", "shared.*", etc
        if pattern.endswith(".*"):
            module_prefix = pattern[:-2]
            # Resolve module name from enum
            try:
                wanted_module = Module(module_prefix)
            except ValueError:
                # Pattern invalido — ignora silenciosamente
                # (futuro: validar na criacao do AgentDefinition)
                continue
            if tool.module == wanted_module:
                return True
        # Match generico via fnmatch (suporta '*', '?')
        elif fnmatch.fnmatch(tool.name, pattern):
            return True
    return False


# Singleton global. Importavel como `from app.agentic.tools.registry import ToolRegistry`.
ToolRegistry = _ToolRegistry()
