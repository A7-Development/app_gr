"""AnthropicAdapter — concrete `LLMAdapter` implementation for Claude.

Translates our internal `Message` shape (`shared/ai/prompts/_base.py`) to the
Anthropic Messages API:

    - `role: "system"` blocks are pulled out and sent in the top-level
      `system` field as a list of content blocks (with `cache_control` to
      activate prompt caching).
    - The first `cache_control` we encounter on a system block is preserved;
      everything else after the system blocks goes to `messages`.
    - Anthropic does not accept a top-level `assistant` message at the
      beginning; if our prompt template emitted one (as in
      `chat.fidc_geral_v1` for the priming "Entendi o contexto..." line),
      we keep it as the first assistant message in `messages`.

Cost calculation uses MVP-baseline pricing for Sonnet (close to median Claude
4 family pricing). Phase 2 will move pricing to a per-model config table.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from app.modules.integracoes.adapters.llm._base import (
    AdapterCallResult,
    LLMAdapter,
    LLMUsage,
)
from app.modules.integracoes.adapters.llm.anthropic.client import AnthropicClient
from app.modules.integracoes.adapters.llm.anthropic.version import ADAPTER_VERSION

# MVP pricing baseline (USD per 1M tokens). Phase 2: load from config table.
_USD_PER_BRL = Decimal("5.00")
_PRICE_USD_PER_M = {
    "input": Decimal("3.00"),
    "output": Decimal("15.00"),
    "cache_write": Decimal("3.75"),  # 1.25x input
    "cache_read": Decimal("0.30"),   # 0.10x input
}


class AnthropicAdapter(LLMAdapter):
    """Calls Claude via Anthropic Messages API with SSE streaming."""

    ADAPTER_VERSION: str = ADAPTER_VERSION

    def __init__(self, *, api_key: str) -> None:
        self._client = AnthropicClient(api_key=api_key)
        self._last_result: AdapterCallResult | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def last_result(self) -> AdapterCallResult | None:
        return self._last_result

    # ------------------------------------------------------------------
    # Stream
    # ------------------------------------------------------------------

    async def chat_stream(
        self,
        *,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Yield assistant text deltas; populate `last_result` on completion."""
        system_blocks, conv_messages = self._split_system_and_messages(messages)

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conv_messages,
        }
        if system_blocks:
            payload["system"] = system_blocks

        request_id: str | None = None
        accumulated: list[str] = []
        usage = LLMUsage()
        stop_reason: str | None = None

        async for event in self._client.stream_messages(payload):
            etype = event.get("type")

            if etype == "message_start":
                msg = event.get("message", {})
                request_id = msg.get("id") or request_id
                u = msg.get("usage") or {}
                usage.tokens_input = int(u.get("input_tokens", 0))
                # cache_creation_input_tokens are billed at write rate, not "cached" hits.
                usage.tokens_cached = int(u.get("cache_read_input_tokens", 0))

            elif etype == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        accumulated.append(text)
                        yield text

            elif etype == "message_delta":
                # Final usage + stop reason arrive here.
                d = event.get("delta") or {}
                stop_reason = d.get("stop_reason") or stop_reason
                u = event.get("usage") or {}
                if "output_tokens" in u:
                    usage.tokens_output = int(u["output_tokens"])

            elif etype == "error":
                err = event.get("error") or {}
                raise RuntimeError(
                    f"Anthropic stream error: {err.get('type', '?')} {err.get('message', '')}"
                )

            # message_stop / content_block_start / content_block_stop: no-op for us.

        self._last_result = AdapterCallResult(
            request_id=request_id or "",
            model=model,
            usage=usage,
            cost_brl=self._compute_cost_brl(usage),
            full_text="".join(accumulated),
            stop_reason=stop_reason,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_system_and_messages(messages: list[dict]) -> tuple[list[dict], list[dict]]:
        """Pull `system` messages into Anthropic's top-level system blocks."""
        system_blocks: list[dict] = []
        conv: list[dict] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "system":
                # Promote each content block to a top-level system block,
                # preserving cache_control if present.
                for c in content or []:
                    block: dict[str, Any] = {"type": "text", "text": c.get("text", "")}
                    if c.get("cache_control"):
                        block["cache_control"] = c["cache_control"]
                    system_blocks.append(block)
            else:
                # Strip cache_control from non-system content (Anthropic rejects it
                # outside system blocks before turn 1).
                clean_content = [
                    {"type": "text", "text": c.get("text", "")}
                    for c in (content or [])
                    if c.get("text")
                ]
                if clean_content:
                    conv.append({"role": role, "content": clean_content})
        return system_blocks, conv

    @staticmethod
    def _compute_cost_brl(usage: LLMUsage) -> Decimal:
        """Convert token usage to BRL using MVP pricing."""
        usd = (
            (Decimal(usage.tokens_input - usage.tokens_cached) / Decimal(1_000_000))
            * _PRICE_USD_PER_M["input"]
            + (Decimal(usage.tokens_cached) / Decimal(1_000_000))
            * _PRICE_USD_PER_M["cache_read"]
            + (Decimal(usage.tokens_output) / Decimal(1_000_000))
            * _PRICE_USD_PER_M["output"]
        )
        return (usd * _USD_PER_BRL).quantize(Decimal("0.000001"))
