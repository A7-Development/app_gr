"""CreditDossierPleito — structured credit request from the commercial team.

The pleito comes informally (email, WhatsApp, call). The analyst structures
it in this row inside the dossier. IA optional helps extract from informal
text via the `pleito_extractor` specialist agent.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class CreditDossierPleito(Base):
    """Structured fields of the credit request."""

    __tablename__ = "credit_dossier_pleito"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    dossier_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("credit_dossier.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # 1-1 with dossier
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Structured fields
    produto: Mapped[str | None] = mapped_column(String(64), nullable=True)
    volume_brl: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True
    )
    taxa: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prazo: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contexto: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgencia: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Source (the original informal communication, kept for audit)
    source_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Texto original informal (email/whats colado pelo analista)"
    )

    # Was the structured form filled by the analyst manually or with IA help?
    extracted_by_ai: Mapped[bool] = mapped_column(default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<CreditDossierPleito dossier={self.dossier_id} produto={self.produto}>"
