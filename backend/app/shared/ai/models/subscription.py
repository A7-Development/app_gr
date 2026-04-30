"""TenantAISubscription: tenant-level entitlement for the AI capability.

Parallel to `tenant_module_subscription` but for the transversal AI capability.
Checked by `core/ai_guard.py::require_ai` on AI endpoints.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class TenantAISubscription(Base):
    """Whether a tenant has the AI capability enabled, plan and caps."""

    __tablename__ = "tenant_ai_subscription"

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    plan_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    monthly_credit_quota: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    hard_cap_brl: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2), nullable=True
    )

    enabled_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<TenantAISubscription tenant={self.tenant_id} "
            f"enabled={self.enabled} plan={self.plan_ref!r}>"
        )
