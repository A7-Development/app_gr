"""CreditDossierBureauQuery — record of a bureau query against a CNPJ or CPF.

Will be populated when bureau adapters are wired (Onda 2). For MVP, the
table exists for FK references but no data flows in yet.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import BureauQueryStatus, BureauSource


class CreditDossierBureauQuery(Base):
    """One bureau query — query against a CNPJ or CPF inside a dossier."""

    __tablename__ = "credit_dossier_bureau_query"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    dossier_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("credit_dossier.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)  # 'company' | 'person'
    entity_ref: Mapped[str] = mapped_column(String(20), nullable=False)   # cnpj or cpf_redacted

    bureau_source: Mapped[BureauSource] = mapped_column(
        SAEnum(
            BureauSource,
            name="credit_bureau_source",
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )

    query_status: Mapped[BureauQueryStatus] = mapped_column(
        SAEnum(
            BureauQueryStatus,
            name="bureau_query_status",
            native_enum=False,
            length=16,
        ),
        nullable=False,
        default=BureauQueryStatus.PENDING,
    )

    queried_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Reference to the bronze (raw) row containing the full payload.
    raw_table_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_row_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    # Canonical silver summary.
    result_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<CreditDossierBureauQuery bureau={self.bureau_source.value} "
            f"entity={self.entity_ref} status={self.query_status.value}>"
        )
