"""Conversation: load + maintain multi-turn chat history server-side.

Responsibilities:
- Create a new `AIConversation` on demand (when chat receives no conversation_id).
- Load the K most recent turns (trimmed by token budget, not count).
- Detect when the conversation should be summarized (turn_count beyond threshold).
- Persist user/AI turns as `AIMessage` rows (redacted text).

Token-budget trimming uses a coarse approximation (4 chars ≈ 1 token), since
the orchestrator already pads its budget. Phase 2 may swap to a real tokenizer.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.ai.models.conversation import AIConversation, AIConversationSummary
from app.shared.ai.models.message import AIMessage, MessageRole

# Above this turn count, the orchestrator should kick off a summary job.
SUMMARIZE_AFTER_TURNS = 20

# How many of the most recent turns we keep verbatim once a summary covers
# the older history.
KEEP_RECENT_TURNS = 10

# Coarse approximation: 4 chars ~ 1 token.
_CHARS_PER_TOKEN = 4


@dataclass(slots=True)
class HistorySegment:
    """One block of context to inject when calling the LLM."""

    role: str           # 'system' | 'user' | 'assistant'
    text: str
    is_summary: bool = False


async def get_or_create_conversation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    conversation_id: UUID | None,
    page_context: str | None,
) -> AIConversation:
    """Return existing conversation or create a new one.

    Verifies tenant + user ownership when `conversation_id` is given (raises
    PermissionError on cross-tenant access).
    """
    if conversation_id is not None:
        conv = await db.get(AIConversation, conversation_id)
        if conv is None:
            raise LookupError(f"AIConversation {conversation_id} not found.")
        if conv.tenant_id != tenant_id or conv.user_id != user_id:
            raise PermissionError(
                f"AIConversation {conversation_id} does not belong to "
                f"user {user_id} of tenant {tenant_id}."
            )
        return conv

    conv = AIConversation(
        tenant_id=tenant_id,
        user_id=user_id,
        page_context=page_context,
    )
    db.add(conv)
    await db.flush()  # populate id
    return conv


async def load_history_for_prompt(
    db: AsyncSession,
    *,
    conversation: AIConversation,
    token_budget: int = 4000,
) -> list[HistorySegment]:
    """Build the segments to inject between system block and the new user msg.

    Order: [optional summary, then most recent turns up to the token budget].

    Returns redacted text only — original (PII) text never leaves the DB to
    the LLM. Tools that need PII recovery use `text_encrypted`.
    """
    segments: list[HistorySegment] = []

    summary = (
        await db.execute(
            select(AIConversationSummary).where(
                AIConversationSummary.conversation_id == conversation.id
            )
        )
    ).scalar_one_or_none()

    if summary is not None:
        segments.append(
            HistorySegment(
                role="user",
                text=f"[Resumo de turns 1..{summary.up_to_turn}]\n{summary.summary_text_redacted}",
                is_summary=True,
            )
        )

    # Pull the most-recent turns (post-summary).
    starting_turn = (summary.up_to_turn + 1) if summary else 1
    rows = (
        await db.execute(
            select(AIMessage)
            .where(
                AIMessage.conversation_id == conversation.id,
                AIMessage.turn_index >= starting_turn,
            )
            .order_by(AIMessage.turn_index.desc())
            .limit(KEEP_RECENT_TURNS * 2)  # user+ai per turn
        )
    ).scalars().all()
    rows.reverse()  # chronological order

    # Trim to token budget (drop oldest first).
    used_chars = sum(len(s.text) for s in segments)
    kept_msgs: list[AIMessage] = []
    for msg in reversed(rows):
        cost = len(msg.text_redacted)
        if (used_chars + cost) // _CHARS_PER_TOKEN > token_budget:
            break
        kept_msgs.append(msg)
        used_chars += cost
    kept_msgs.reverse()

    for msg in kept_msgs:
        role = "user" if msg.role == MessageRole.USER else "assistant"
        segments.append(HistorySegment(role=role, text=msg.text_redacted))

    return segments


async def append_message(
    db: AsyncSession,
    *,
    conversation: AIConversation,
    role: MessageRole,
    text_redacted: str,
    text_encrypted: bytes | None = None,
    usage_event_id: UUID | None = None,
) -> AIMessage:
    """Append a turn and bump the conversation's counters.

    Caller commits. Returns the persisted message.
    """
    conversation.turn_count = (conversation.turn_count or 0) + 1
    msg = AIMessage(
        conversation_id=conversation.id,
        turn_index=conversation.turn_count,
        role=role,
        text_redacted=text_redacted,
        text_encrypted=text_encrypted,
        usage_event_id=usage_event_id,
    )
    db.add(msg)
    await db.flush()
    return msg


def needs_summary(conversation: AIConversation) -> bool:
    """Whether we should enqueue a summary job for the conversation."""
    return (conversation.turn_count or 0) >= SUMMARIZE_AFTER_TURNS
