"""Copiloto (Strata AI) endpoints — free-form chat surface.

Mounted at `/copiloto` from `api/v1/router.py`. Spec: specs/active/copiloto-mcp.md.
The AIPanel chat (`/ai/chat`) is untouched — the Strata AI is born on its own
endpoint (spec §7, regression guard).

SSE wire format (same as `/ai/chat`):

    event: <type>
    data: <json>
    \\n
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_guard import require_ai
from app.core.database import get_db
from app.core.enums import AICapability
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.ai.schemas import CopilotoChatRequest
from app.shared.ai.services.copiloto import stream_copiloto_response

router = APIRouter(prefix="/copiloto", tags=["copiloto"])


@router.post("/chat")
async def copiloto_chat(
    payload: CopilotoChatRequest,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_ai(AICapability.READ))],
) -> StreamingResponse:
    """Stream one Strata AI chat turn as text/event-stream."""

    async def event_stream() -> AsyncIterator[bytes]:
        async for event in stream_copiloto_response(
            db=db,
            principal=principal,
            user_message=payload.message,
            conversation_id=payload.conversation_id,
        ):
            event_type = event.get("type", "delta")
            payload_json = json.dumps(
                {k: v for k, v in event.items() if k != "type"},
                ensure_ascii=False,
            )
            frame = f"event: {event_type}\ndata: {payload_json}\n\n"
            yield frame.encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


__all__ = ["router"]
