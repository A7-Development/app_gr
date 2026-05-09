"""HttpRequestNode — calls an external HTTP API and returns the response.

Generic node that proves the platform is extensible beyond IA — the same
shape any future "API integration" node would take. All config fields
support template substitution (resolved by the engine before execution).

Config schema:
    {
        "method": "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
        "url": "https://...",
        "headers": {"X-Auth": "{{trigger.token}}"},  # optional, templated
        "json_body": {...},                          # optional, templated, sent as JSON
        "query_params": {...},                       # optional, templated
        "timeout_seconds": 30                        # optional, default 30
    }

Output:
    {
        "status_code": int,
        "ok": bool,                # 2xx
        "body": ... | str,         # parsed JSON if response is application/json,
                                   # else text (truncated to 10kb)
        "headers": {...}
    }

Errors (timeout, network) raise — the node fails (engine catches).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.workflow.nodes._base import BaseNode, NodeContext, NodeOutput

logger = logging.getLogger(__name__)

_VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_BODY_TRUNCATE_BYTES = 10_240


class HttpRequestNode(BaseNode):
    """Calls an external HTTP API."""

    type = "http_request"

    def validate_config(self) -> None:
        method = (self.config.get("method") or "GET").upper()
        if method not in _VALID_METHODS:
            raise ValueError(
                f"http_request: invalid method '{method}'. "
                f"Use one of {sorted(_VALID_METHODS)}."
            )
        if not self.config.get("url"):
            raise ValueError("http_request: `config.url` is required")

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        method = (self.config.get("method") or "GET").upper()
        url = str(self.config["url"])
        headers = self.config.get("headers") or {}
        json_body = self.config.get("json_body")
        query_params = self.config.get("query_params") or {}
        timeout = float(self.config.get("timeout_seconds") or 30.0)

        # Coerce header values to str (templates may resolve to int/None).
        clean_headers: dict[str, str] = {}
        for k, v in headers.items():
            if v is None:
                continue
            clean_headers[str(k)] = str(v)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                url,
                headers=clean_headers or None,
                params=query_params or None,
                json=json_body if json_body else None,
            )

        body: Any = None
        ctype = response.headers.get("content-type", "").lower()
        if "application/json" in ctype:
            try:
                body = response.json()
            except ValueError:
                body = response.text[:_BODY_TRUNCATE_BYTES]
        else:
            body = response.text[:_BODY_TRUNCATE_BYTES]

        return NodeOutput(
            data={
                "status_code": response.status_code,
                "ok": 200 <= response.status_code < 300,
                "body": body,
                "headers": dict(response.headers),
            },
            status_hint=f"HTTP {response.status_code}",
        )
