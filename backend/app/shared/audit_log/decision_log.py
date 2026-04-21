"""DecisionLog: append-only record of every decision/calculation/sync (CLAUDE.md 14.2)."""

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class DecisionType(enum.StrEnum):
    """Type of decision logged."""

    SYNC = "sync"
    CALCULATION = "calculation"
    ALERT = "alert"
    RECOMMENDATION = "recommendation"
    SCORE = "score"
    RECONCILIATION_CHECK = "reconciliation_check"
    RULE_EVALUATION = "rule_evaluation"


class DecisionLog(Base):
    """Append-only log of every system decision / calculation / sync.

    Rules:
        - No UPDATE, no DELETE (enforced by convention; enforce via trigger later).
        - Corrections are NEW entries that reference the previous via `supersedes`.
    """

    __tablename__ = "decision_log"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    decision_type: Mapped[DecisionType] = mapped_column(
        SAEnum(DecisionType, name="decision_type", native_enum=False, length=32),
        nullable=False,
        index=True,
    )

    inputs_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rule_or_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rule_or_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    triggered_by: Mapped[str] = mapped_column(String(128), nullable=False)

    # Versioning link: if this decision supersedes another (correction), reference it
    supersedes: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("decision_log.id"), nullable=True
    )

    # Reference to premise set used, if any
    premise_set_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("premise_set.id"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<DecisionLog id={self.id} type={self.decision_type.value} tenant={self.tenant_id}>"
