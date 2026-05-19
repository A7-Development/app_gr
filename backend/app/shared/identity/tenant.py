"""Tenant: root of multi-tenant isolation."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import TenantStatus


class Tenant(Base):
    """A tenant = an isolated organization using GR.

    Every domain row carries `tenant_id` FK to this table.
    """

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subdomain: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)

    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )

    # Marks the single tenant that operates the system (the maintainer).
    # Constrained to at most one row with `true` via partial unique index.
    # Required to access global admin endpoints (AI provider credentials, tenant AI tier
    # management, prompt library) — see core/system_maintainer_guard.py.
    is_system_maintainer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Lifecycle do tenant (trial/active/suspended/cancelled). Suspended/cancelled
    # bloqueia login. Default 'active' pra back-compat; novos tenants criados
    # via /admin/tenants podem nascer em 'trial' com prazo.
    status: Mapped[TenantStatus] = mapped_column(
        SAEnum(TenantStatus, name="tenant_status", native_enum=False, length=16),
        nullable=False,
        default=TenantStatus.ACTIVE,
        server_default=TenantStatus.ACTIVE.value,
        index=True,
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    users: Mapped[list["User"]] = relationship(  # noqa: F821
        back_populates="tenant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} slug={self.slug!r}>"
