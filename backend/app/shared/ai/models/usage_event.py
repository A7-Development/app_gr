"""AIUsageEvent: append-only metering of every AI call.

Idempotent by `request_id` (unique). The chat orchestrator (`services/chat.py`)
is the only writer in the request path; admin reports read aggregates.

Partitioning: monthly RANGE on `occurred_at` will be enabled in Phase 2 of the
plan. MVP keeps a single table with the index on (tenant_id, occurred_at DESC).
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import AIProvider, AIUsageStatus, Module


class AIUsageEvent(Base):
    """One row per AI call (success or failure). Source of truth for billing."""

    __tablename__ = "ai_usage_event"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    request_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    feature: Mapped[str] = mapped_column(String(64), nullable=False)
    context_module: Mapped[Module | None] = mapped_column(
        SAEnum(Module, name="module", native_enum=False, length=32, create_type=False),
        nullable=True,
    )

    provider: Mapped[AIProvider] = mapped_column(
        SAEnum(AIProvider, name="ai_provider", native_enum=False, length=32, create_type=False),
        nullable=False,
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_template_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    tokens_input: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tokens_output: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tokens_cached: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    cost_brl_provider: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=6), nullable=False, default=0, server_default="0"
    )
    cost_credits_billed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    status: Mapped[AIUsageStatus] = mapped_column(
        SAEnum(AIUsageStatus, name="ai_usage_status", native_enum=False, length=32),
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    decision_log_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("decision_log.id"), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<AIUsageEvent id={self.id} tenant={self.tenant_id} "
            f"feature={self.feature!r} status={self.status.value}>"
        )
