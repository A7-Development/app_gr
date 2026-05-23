"""PlaybookNotification — record of notification dispatched by a workflow.

MVP: just persists the intent. Channels supported in MVP:
- "log"   — written to decision_log (already-recorded) + this row
- "email" — placeholder; recorded but NOT actually sent (needs SES/SMTP)

Future: webhook, SMS, push, in-app inbox.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class PlaybookNotification(Base):
    """One notification dispatched (or recorded) during a workflow run."""

    __tablename__ = "workflow_notification"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(String(128), nullable=False)

    channel: Mapped[str] = mapped_column(String(32), nullable=False)  # 'log', 'email', etc.
    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    delivered: Mapped[bool] = mapped_column(default=False, server_default="false")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<PlaybookNotification {self.channel} to={self.recipient!r}>"
