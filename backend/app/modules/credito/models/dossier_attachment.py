"""DossierAttachment — files attached to a dossier (optionally per step).

Each row represents a file uploaded by an analyst during the credit analysis.
The file blob lives on the filesystem under `DOSSIER_STORAGE_ROOT`; the row
holds metadata + storage_key + sha256 for dedup.

`node_id` is nullable: a NULL value means the attachment belongs to the
dossier as a whole (no specific step). When set, the right-rail Evidence
panel filters that attachment to the matching step in focus.

Multi-tenant: every query MUST scope by `tenant_id`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class DossierAttachment(Base):
    """A file attached to a credit dossier (optionally pinned to a step)."""

    __tablename__ = "credit_dossier_attachment"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    dossier_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("credit_dossier.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Step pinning. NULL = anexo do dossie (nao de step especifico).
    node_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # File metadata
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Optional caption supplied by the uploader.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Ownership / audit
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

    def __repr__(self) -> str:
        return (
            f"<DossierAttachment id={self.id} dossier={self.dossier_id} "
            f"node={self.node_id} filename={self.filename!r}>"
        )
