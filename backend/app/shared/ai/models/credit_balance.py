"""AICreditBalance: monthly credit accounting per tenant.

Composite PK (tenant_id, period_yyyymm). Each month, a new row is opened
(by a job at month start) carrying the plan grant + carryover from the
previous month. `consumed` is incremented by `services/metering.py` on
every successful AI call. `topup` is set by admin endpoint when the tenant
buys extra credits.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AICreditBalance(Base):
    """Per-tenant per-month credit ledger."""

    __tablename__ = "ai_credit_balance"

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    period_yyyymm: Mapped[str] = mapped_column(String(7), primary_key=True)  # '2026-04'

    granted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    carryover: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    topup: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    @property
    def remaining(self) -> int:
        return self.granted + self.carryover + self.topup - self.consumed

    def __repr__(self) -> str:
        return (
            f"<AICreditBalance tenant={self.tenant_id} period={self.period_yyyymm} "
            f"remaining={self.remaining}>"
        )
