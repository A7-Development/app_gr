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
from app.core.enums import Environment, SourceType


class TenantSourceConfig(Base):
    """Tenant-specific config for a given source + environment.

    Example (Bitfin ERP): contains connection string, filter (cnpj), field mappings.
    Example (QiTech admin): contains api_key, client private key PEM, base URL.

    The `config` JSONB is stored as an envelope (see `app.shared.crypto.envelope`);
    plaintext decryption is centralized in `services.source_config`.

    `environment` lets the same tenant keep a sandbox and a production config
    coexisting for the same source_type without clobbering each other.
    """

    __tablename__ = "tenant_source_config"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_type", "environment", name="uq_tenant_source_env"
        ),
    )

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
    environment: Mapped[Environment] = mapped_column(
        SAEnum(Environment, name="environment", native_enum=False, length=16),
        nullable=False,
        default=Environment.PRODUCTION,
        server_default=Environment.PRODUCTION.name,
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
            f"source={self.source_type.value} env={self.environment.value} "
            f"enabled={self.enabled}>"
        )
