"""Auditable mixin.

Every warehouse row that stores externally-ingested data MUST use this mixin
(see CLAUDE.md section 14.1). Domain tables (tenant, user, etc) do NOT need it.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.enums import SourceType, TrustLevel


class Auditable:
    """Adds proveniencia (lineage) columns.

    Usage:

        class NfeCabecalho(Auditable, Base):
            __tablename__ = "nfe_cabecalho"
            id: Mapped[UUID] = mapped_column(primary_key=True)
            ...
    """

    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type", native_enum=False, length=64),
        nullable=False,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    hash_origem: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingested_by_version: Mapped[str] = mapped_column(String(128), nullable=False)
    trust_level: Mapped[TrustLevel] = mapped_column(
        SAEnum(TrustLevel, name="trust_level", native_enum=False, length=16),
        nullable=False,
        default=TrustLevel.HIGH,
    )
    collected_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
