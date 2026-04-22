"""TenantSourceConfig: per-tenant configuration for a given source (credentials, filters).

Owned by `integracoes` module — only integracoes reads or writes this table. Other modules
that need to know whether a source is enabled for a tenant must call
`integracoes.public.is_source_enabled()` (contract), not query this table directly.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import SourceType


class TenantSourceConfig(Base):
    """Tenant-specific config for a given source.

    Example (Bitfin ERP): contains connection string, filter (cnpj), field mappings.
    Example (QiTech admin): contains api_key, subscription_id.

    Secrets are stored plaintext in MVP; `source_config` service applies a no-op
    encrypt/decrypt wrapper that can be swapped for real encryption later without
    call-site changes.
    """

    __tablename__ = "tenant_source_config"
    __table_args__ = (UniqueConstraint("tenant_id", "source_type", name="uq_tenant_source"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type", native_enum=False, length=64),
        ForeignKey("source_catalog.source_type"),
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sync_frequency_minutes: Mapped[int | None] = mapped_column(nullable=True)

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
            f"<TenantSourceConfig tenant={self.tenant_id} "
            f"source={self.source_type.value} enabled={self.enabled}>"
        )
