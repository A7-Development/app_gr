"""Tools do modulo cadastros (party model / entidades).

Importacao explicita pra forcar execucao dos decorators `@register_tool`
no momento em que o pacote `app.agentic.tools` e carregado.
"""

from app.agentic.tools.cadastros import entidades  # noqa: F401
