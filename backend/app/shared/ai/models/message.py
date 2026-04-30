"""AIMessage: one turn (user or AI) inside an AIConversation.

Stores the redacted text inline and the original (PII-bearing) text encrypted
at rest with envelope encryption. The redacted version is what gets re-injected
when building context for follow-up turns and what's shown in audit UI without
extra permission. The encrypted version is recoverable via DSAR / regulatory
request and accessible only by maintainer admins with audited access.
"""

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class MessageRole(enum.StrEnum):
    """Who sent the message."""

    USER = "user"
    AI = "ai"


class AIMessage(Base):
    """One turn of an AIConversation (user input or AI response)."""

    __tablename__ = "ai_message"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ai_conversation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)

    role: Mapped[MessageRole] = mapped_column(
        SAEnum(MessageRole, name="ai_message_role", native_enum=False, length=16),
        nullable=False,
    )

    text_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    # Phase 2: cipher original text via envelope. MVP leaves nullable.
    text_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    usage_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_usage_event.id"), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<AIMessage id={self.id} conv={self.conversation_id} "
            f"turn={self.turn_index} role={self.role.value}>"
        )
