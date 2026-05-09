"""CreditDocumentTemplate — per-tenant template guiding document extraction.

Each tenant defines its own templates for the various document types
(DRE, balance sheet, commercial visit report, etc). When uploading a
document, the user can select which template to apply — the
document_extractor agent then uses `instructions` + `fields_schema` to
produce a structured extraction.

Templates with `tenant_id IS NULL` are starter packs provided by Strata
that any tenant can use as-is or clone and customize.

Without a selected template, the document extractor runs in free-form mode
(extracts whatever appears relevant).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import DocumentType


class CreditDocumentTemplate(Base):
    """Per-tenant template guiding document extraction by the IA."""

    __tablename__ = "credit_document_template"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # NULL tenant_id = Strata starter pack; non-null = tenant-owned.
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    doc_type: Mapped[DocumentType] = mapped_column(
        SAEnum(
            DocumentType,
            name="credit_document_type",
            native_enum=False,
            length=32,
            create_type=False,  # type already exists from credit_dossier_document
        ),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Free-form schema describing the expected extracted fields.
    # Example: { "campos": [{"nome": "data_visita", "tipo": "date", "obrigatorio": true}, ...] }
    # The extractor agent reads this to know what to look for.
    fields_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Free-form instructions to the extractor agent. Tenant-specific guidance
    # (ex: "este documento e o template Onboard da A7 — extraia data, responsavel
    # pela visita, observacoes sobre instalacoes, ...").
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
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
        scope = f"tenant={self.tenant_id}" if self.tenant_id else "starter"
        return f"<CreditDocumentTemplate {self.name!r} ({self.doc_type.value}, {scope})>"
