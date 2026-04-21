"""PremiseSet: versioned collection of assumptions used in calculations/projections."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class PremiseSet(Base):
    """Versioned set of premisses (rates, tolerances, cutoffs, scenarios).

    Rules:
        - Each edit creates a NEW version (same `key`, incremented `version`).
        - Calculations reference the exact `premise_set_id` used.
        - History preserved for replay (CLAUDE.md 14.3 / 14.4).
    """

    __tablename__ = "premise_set"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", "version", name="uq_premise_set_key_version"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    premises: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<PremiseSet key={self.key!r} v={self.version} tenant={self.tenant_id}>"
