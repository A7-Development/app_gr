"""Anthropic adapter — Claude family via Messages API + SSE streaming."""

from app.modules.integracoes.adapters.llm.anthropic.adapter import AnthropicAdapter
from app.modules.integracoes.adapters.llm.anthropic.version import ADAPTER_VERSION

__all__ = ["ADAPTER_VERSION", "AnthropicAdapter"]
