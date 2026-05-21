"""Tools compartilhadas (calc, reference) — usaveis cross-modulo.

Importacao explicita pra forcar execucao dos decorators `@register_tool`
no momento em que o pacote `app.agentic.tools` e carregado.
"""

from app.agentic.tools.shared import calc  # noqa: F401
