"""CreditDossierDocument — documents uploaded to a dossier.

Lifecycle:
1. Analyst uploads — file is saved to filesystem, row created with status=pending.
2. document_extractor agent processes the file — fills `ai_extraction`.
3. Specialist agents read `ai_extraction` via `get_document_extraction` tool.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import DocumentType


class CreditDossierDocument(Base):
    """One uploaded document linked to a dossier."""

    __tablename__ = "credit_dossier_document"

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

    doc_type: Mapped[DocumentType] = mapped_column(
        SAEnum(
            DocumentType,
            name="credit_document_type",
            native_enum=False,
            length=32,
        ),
        nullable=False,
        index=True,
    )

    # File storage — filesystem path relative to the upload root.
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    uploaded_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ─── Extraction ──────────────────────────────────────────────────────
    extraction_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_extraction: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ai_model_used: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(
        Numeric(precision=4, scale=3), nullable=True
    )
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional links — when a doc is tied to a specific person/company.
    linked_person_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("credit_dossier_person.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_company_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("credit_dossier_company.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CreditDossierDocument id={self.id} type={self.doc_type.value} "
            f"file={self.original_filename!r}>"
        )
