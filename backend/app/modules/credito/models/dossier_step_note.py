"""DossierStepNote — analyst notes pinned to a specific step of a dossier.

Each note is always tied to a `node_id` (no global notes — the dossier root
already has `notes` on `CreditDossier` for that). Notes carry markdown body
(rendered via react-markdown + remark-gfm on the frontend).

`pinned=True` notes float to the top of the list in the Evidence right-rail.
Author can edit/delete; admins of the tenant can also delete.

Multi-tenant: every query MUST scope by `tenant_id`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class DossierStepNote(Base):
    """A markdown note attached to one step of a dossier workflow."""

    __tablename__ = "credit_dossier_step_note"

    __table_args__ = (
        CheckConstraint(
            "char_length(body_md) BETWEEN 1 AND 10000",
            name="ck_dossier_step_note_body_md_length",
        ),
    )

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

    # Always tied to a specific step.
    node_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    body_md: Mapped[str] = mapped_column(Text, nullable=False)

    pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    # Authorship
    author_id: Mapped[UUID | None] = mapped_column(
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
        return (
            f"<DossierStepNote id={self.id} dossier={self.dossier_id} "
            f"node={self.node_id} pinned={self.pinned}>"
        )
