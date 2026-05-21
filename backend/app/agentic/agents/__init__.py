"""Camada de agentes — composicao runtime persona + expertise + prompt + CATALOG metadata.

Hoje (F2.b.2) carrega 3 modulos:
    _base.py     ResolvedAgent dataclass (composto resolvido em runtime)
    _compose.py  compose_system_text() — XML tags + markdown
    registry.py  AgentRegistry.get() — DB-first com fallback CATALOG

O catalogo central de definicoes vive em DB (`agent_definition`), seedado
em F2.b.1. Estrutura tipada (output_schema, inputs, allowed_tools)
continua em codigo no `app/agentic/engine/catalog.py`. Linha clara:
texto editavel = DB; estrutura tipada Python = CATALOG.

Vocabulario:
    AgentDefinition       = SQLAlchemy model (row de `agent_definition`)
    ResolvedAgent         = composto Python pronto pra runtime (persona +
                            expertises + prompt + spec do CATALOG)

Ver CLAUDE.md §19.12 (catalogo central de agentes).
"""

from app.agentic.agents._base import ResolvedAgent
from app.agentic.agents._compose import compose_system_text
from app.agentic.agents.registry import AgentNotFoundError, AgentRegistry

__all__ = [
    "AgentNotFoundError",
    "AgentRegistry",
    "ResolvedAgent",
    "compose_system_text",
]
