"""DossierStepLink — external URL references attached to a dossier or step.

The analyst pastes URLs of relevant external sources (online statements,
client portals, third-party documents) and tags them to a specific step
or to the dossier as a whole (`node_id IS NULL`).

`title` is captured by the analyst at paste time. Future: auto-fetch via
OG tags. The MVP just stores hostname-derived placeholder when title is
absent on the frontend.

Multi-tenant: every query MUST scope by `tenant_id`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class DossierStepLink(Base):
    """A URL reference attached to a dossier or step."""

    __tablename__ = "credit_dossier_step_link"

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

    # NULL = link de dossie (nao de step especifico).
    node_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    added_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<DossierStepLink id={self.id} dossier={self.dossier_id} "
            f"node={self.node_id} url={self.url!r}>"
        )
