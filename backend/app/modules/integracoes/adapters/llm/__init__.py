"""LLM adapters — versioned wrappers over external LLM providers.

Follows CLAUDE.md sec 13 (adapter pattern). Each provider is one adapter
under `<provider>/` with its own `ADAPTER_VERSION`. Configuration (API key)
is loaded from the global `ai_provider_credential` table; no per-tenant
credentials, since LLM keys are managed centrally by the system maintainer
(CLAUDE.md sec 19, plan 2026-04-30).
"""

from app.modules.integracoes.adapters.llm._base import (
    AdapterCallResult,
    LLMAdapter,
    LLMUsage,
)

__all__ = ["AdapterCallResult", "LLMAdapter", "LLMUsage"]
