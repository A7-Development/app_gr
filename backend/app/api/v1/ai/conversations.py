"""GET/DELETE /api/v1/ai/conversations — chat history for the user."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_guard import require_ai
from app.core.database import get_db
from app.core.enums import AICapability
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.ai.models.conversation import AIConversation
from app.shared.ai.models.message import AIMessage
from app.shared.ai.schemas import ConversationListItem, ConversationMessageRead

router = APIRouter()


@router.get("/conversations", response_model=list[ConversationListItem])
async def list_conversations(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_ai(AICapability.READ))],
    limit: int = 20,
    include_archived: bool = False,
    surface: str | None = None,
) -> list[ConversationListItem]:
    """Return the user's chat conversations, most-recent first.

    `surface` filters by owning chat UI ("aipanel" | "copiloto"); omitted =
    all surfaces (backward compatible).
    """
    stmt = (
        select(AIConversation)
        .where(
            AIConversation.tenant_id == principal.tenant_id,
            AIConversation.user_id == principal.user_id,
        )
        .order_by(AIConversation.last_msg_at.desc())
        .limit(min(max(1, limit), 200))
    )
    if not include_archived:
        stmt = stmt.where(AIConversation.archived_at.is_(None))
    if surface is not None:
        stmt = stmt.where(AIConversation.surface == surface)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        ConversationListItem(
            id=r.id,
            title=r.title,
            page_context=r.page_context,
            last_msg_at=r.last_msg_at,
            turn_count=r.turn_count,
        )
        for r in rows
    ]


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[ConversationMessageRead],
)
async def list_messages(
    conversation_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_ai(AICapability.READ))],
) -> list[ConversationMessageRead]:
    """Return redacted turns of a conversation, in chronological order."""
    conv = await db.get(AIConversation, conversation_id)
    if conv is None or conv.user_id != principal.user_id or conv.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversa nao encontrada."
        )

    rows = (
        await db.execute(
            select(AIMessage)
            .where(AIMessage.conversation_id == conversation_id)
            .order_by(AIMessage.turn_index.asc())
        )
    ).scalars().all()

    return [
        ConversationMessageRead(
            id=r.id,
            turn_index=r.turn_index,
            role=r.role.value,
            text=r.text_redacted,
            occurred_at=r.occurred_at,
        )
        for r in rows
    ]


class ConversationRename(BaseModel):
    """Body de PATCH /conversations/{id} — renomear (rail do Copiloto, Fase 4)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)


@router.patch("/conversations/{conversation_id}", response_model=ConversationListItem)
async def rename_conversation(
    conversation_id: UUID,
    payload: ConversationRename,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_ai(AICapability.READ))],
) -> ConversationListItem:
    """Renomeia a conversa (ownership verificada — mesmo criterio do delete)."""
    conv = await db.get(AIConversation, conversation_id)
    if conv is None or conv.user_id != principal.user_id or conv.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversa nao encontrada."
        )
    conv.title = payload.title.strip()
    await db.commit()
    return ConversationListItem(
        id=conv.id,
        title=conv.title,
        page_context=conv.page_context,
        last_msg_at=conv.last_msg_at,
        turn_count=conv.turn_count,
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_conversation(
    conversation_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_ai(AICapability.READ))],
) -> None:
    """Soft-delete (LGPD). Hard-delete is via DSAR endpoint (Phase 3)."""
    conv = await db.get(AIConversation, conversation_id)
    if conv is None or conv.user_id != principal.user_id or conv.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversa nao encontrada."
        )
    conv.archived_at = datetime.now(UTC)
    await db.commit()
