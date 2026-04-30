"""Low-level HTTP client for Anthropic Messages API.

Async streaming over SSE using httpx. Handles:
    - Standard auth headers (`x-api-key`, `anthropic-version`).
    - Optional ZDR header (Anthropic enables ZDR contract-side, but we send
      `anthropic-version: 2023-06-01` consistently).
    - SSE event parsing — yields raw event dicts (caller filters by type).
    - Retry on 429 / 5xx with exponential backoff (max 3 attempts).

It does NOT implement business logic (tokens, costs, prompt caching shape).
That lives in adapter.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import AsyncIterator
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


class AnthropicHTTPError(Exception):
    """Raised when the Anthropic API returns an unrecoverable error."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"Anthropic HTTP {status_code}: {body[:512]}")
        self.status_code = status_code
        self.body = body


class AnthropicClient:
    """Thin async wrapper. One instance per AnthropicAdapter."""

    def __init__(self, *, api_key: str, max_retries: int = 3) -> None:
        self._api_key = api_key
        self._max_retries = max_retries
        self._http = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def stream_messages(self, payload: dict[str, Any]) -> AsyncIterator[dict]:
        """Send a /v1/messages call with `stream=True`, yielding parsed SSE events.

        Each yielded dict is the JSON-decoded `data:` of an SSE line. The caller
        switches on `event["type"]` (`message_start`, `content_block_delta`,
        `message_delta`, `message_stop`, `error`).
        """
        body = {**payload, "stream": True}
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
            "accept": "text/event-stream",
        }

        attempt = 0
        while True:
            attempt += 1
            try:
                async with self._http.stream(
                    "POST", ANTHROPIC_API_URL, json=body, headers=headers
                ) as resp:
                    if resp.status_code in (429, 500, 502, 503, 504):
                        # Drain body for the log; then back off.
                        text = await resp.aread()
                        if attempt >= self._max_retries:
                            raise AnthropicHTTPError(resp.status_code, text.decode("utf-8", "replace"))
                        delay = (2**attempt) + random.random()
                        logger.warning(
                            "Anthropic transient %s on attempt %d/%d, sleeping %.1fs",
                            resp.status_code, attempt, self._max_retries, delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    if resp.status_code >= 400:
                        text = await resp.aread()
                        raise AnthropicHTTPError(
                            resp.status_code, text.decode("utf-8", "replace")
                        )

                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_part = line[len("data:") :].strip()
                        if not data_part:
                            continue
                        try:
                            yield json.loads(data_part)
                        except json.JSONDecodeError:
                            logger.warning("Skipping malformed SSE line: %r", data_part[:200])
                            continue
                    return  # iterator finished cleanly
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as e:
                if attempt >= self._max_retries:
                    raise
                delay = (2**attempt) + random.random()
                logger.warning(
                    "Anthropic transport error (%s) on attempt %d/%d, sleeping %.1fs",
                    type(e).__name__, attempt, self._max_retries, delay,
                )
                await asyncio.sleep(delay)
