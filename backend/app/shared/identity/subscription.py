"""TenantModuleSubscription: which modules are enabled for which tenant."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import Module


class TenantModuleSubscription(Base):
    """Which GR modules are enabled for a given tenant.

    Checked by `require_module` on every endpoint of a module.
    Disabled subscription -> HTTP 402 Payment Required.
    """

    __tablename__ = "tenant_module_subscription"

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    module: Mapped[Module] = mapped_column(
        SAEnum(Module, name="module", native_enum=False, length=32),
        primary_key=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    enabled_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    plan_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

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
            f"<Subscription tenant={self.tenant_id} "
            f"module={self.module.value} enabled={self.enabled}>"
        )
