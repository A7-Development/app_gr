"""LLMAdapter — abstract interface for any LLM provider.

Subclasses (anthropic/, openai/) implement `chat_stream`, returning an async
iterator of text deltas plus a final `AdapterCallResult` (with token counts
and provider request id). The orchestrator (`shared/ai/services/chat.py`)
treats all providers uniformly through this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class LLMUsage:
    """Token usage for a single LLM call."""

    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cached: int = 0  # cache hits (Anthropic)


@dataclass(slots=True)
class AdapterCallResult:
    """Final state of an LLM call returned by the adapter."""

    request_id: str
    model: str
    usage: LLMUsage
    cost_brl: Decimal
    full_text: str  # concatenated deltas
    stop_reason: str | None = None


class LLMAdapter(ABC):
    """Abstract LLM provider adapter.

    Implementations must be async + non-blocking (use httpx async).
    """

    ADAPTER_VERSION: str = "abstract"

    @abstractmethod
    async def chat_stream(
        self,
        *,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream the assistant response as text deltas.

        Yields text chunks. After the iterator is exhausted, the implementation
        sets `last_result` so the caller can read final usage + request_id.
        """
        # Unreachable; ABC with `yield` to satisfy the AsyncIterator return type.
        if False:
            yield ""
        raise NotImplementedError

    @property
    @abstractmethod
    def last_result(self) -> AdapterCallResult | None:
        """Final result of the most recent `chat_stream` (None before first call)."""

    @abstractmethod
    async def aclose(self) -> None:
        """Release the underlying HTTP client."""
