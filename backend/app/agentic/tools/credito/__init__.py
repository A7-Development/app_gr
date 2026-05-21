"""Tools especificas do modulo Credito.

Importacao explicita pra forcar execucao dos decorators `@register_tool`
no momento em que o pacote `app.agentic.tools` e carregado.
"""

from app.agentic.tools.credito import document, dossier  # noqa: F401
