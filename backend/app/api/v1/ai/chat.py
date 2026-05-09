"""POST /api/v1/ai/chat — SSE-streamed multi-turn chat.

Each event sent over the wire is encoded as:

    event: <type>
    data: <json>
    \\n

Event types map 1:1 to the dicts yielded by `services/chat.py::stream_chat_response`.
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
from app.shared.ai.schemas import ChatRequest
from app.shared.ai.services.chat import stream_chat_response

router = APIRouter()


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_ai(AICapability.READ))],
) -> StreamingResponse:
    """Stream the AI response as text/event-stream."""

    async def event_stream() -> AsyncIterator[bytes]:
        async for event in stream_chat_response(
            db=db,
            principal=principal,
            user_message=payload.message,
            page_context=payload.context.page,
            period=payload.context.period,
            filters=payload.context.filters,
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
