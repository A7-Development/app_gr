"""SourceCatalog: registry of known external data sources (ERP, admin APIs, bureaus, parsers).

Adding a new source = new row here + new adapter in `modules/integracoes/adapters/`.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import SourceType


class SourceCatalog(Base):
    """Metadata about each source the system can ingest from.

    Global (not tenant-scoped): same catalog shared across tenants.
    Per-tenant config (credentials, filters) lives in `TenantSourceConfig`.
    """

    __tablename__ = "source_catalog"

    # Primary key = the source_type value (e.g., "erp:bitfin")
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type", native_enum=False, length=64),
        primary_key=True,
    )

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # e.g., "erp", "admin", "bureau_pf", "bureau_pj", "document"
    owner_org: Mapped[str | None] = mapped_column(String(128), nullable=True)

    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_cost_brl: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    # Descriptor of expected inputs/outputs (useful for docs and UI)
    inputs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    outputs: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)

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
        return f"<SourceCatalog {self.source_type.value} category={self.category}>"
