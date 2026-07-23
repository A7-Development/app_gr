"""AIConversation + AIConversationSummary: multi-turn chat history.

A conversation groups N AIMessage rows by `conversation_id`. When the turn
count exceeds a threshold, a background job summarizes early turns into an
`ai_conversation_summary` row, which is injected in place of those turns when
the orchestrator builds the prompt for the LLM. The original `ai_message`
rows are preserved for audit.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AIConversation(Base):
    """A multi-turn chat session between a user and the AI."""

    __tablename__ = "ai_conversation"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Auto-generated title (suggested by AI after the 3rd turn). Nullable
    # because the first 2 turns may finish before titling runs.
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_context: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Which chat surface owns this conversation: "aipanel" (BI drawer) or
    # "copiloto" (Strata AI full page). Rails filter by this so the two
    # histories never mix (spec copiloto-mcp §6.5).
    surface: Mapped[str] = mapped_column(
        String(32), nullable=False, default="aipanel", server_default="aipanel"
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_msg_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    turn_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Soft-delete (LGPD). Hard-delete via DSAR endpoint.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AIConversation id={self.id} user={self.user_id} "
            f"turns={self.turn_count} title={self.title!r}>"
        )


class AIConversationSummary(Base):
    """Compressed summary of early turns of a long conversation.

    When `AIConversation.turn_count` exceeds the threshold, a background job
    summarizes turns 1..up_to_turn into one entry. The orchestrator then uses
    `(summary, turns up_to_turn+1..now, user_msg)` as context, keeping the LLM
    prompt within the token budget while preserving conversational coherence.
    """

    __tablename__ = "ai_conversation_summary"

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ai_conversation.id", ondelete="CASCADE"),
        primary_key=True,
    )

    up_to_turn: Mapped[int] = mapped_column(Integer, nullable=False)

    # Same redacted/encrypted dual-storage as AIMessage.
    summary_text_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    summary_text_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    generated_by_prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<AIConversationSummary conv={self.conversation_id} "
            f"up_to_turn={self.up_to_turn}>"
        )
