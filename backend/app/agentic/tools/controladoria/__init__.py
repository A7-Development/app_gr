"""Controladoria tools — registradas no ToolRegistry no import.

Import deste pacote forca os decorators `@register_tool` nas tools de
cota_sub.py, que registram no `ToolRegistry` global.
"""

from app.agentic.tools.controladoria import cota_sub  # noqa: F401
