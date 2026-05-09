"""CreditDossierAnalysis — output of a specialist agent for a section.

Each row is one section's analysis (created by a specialist_agent node) +
analyst's notes/approval.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class CreditDossierAnalysis(Base):
    """The analysis output for a section — IA result + analyst overrides."""

    __tablename__ = "credit_dossier_analysis"

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

    # Section identifier — matches `SpecialistAgentSpec.section_id` in the catalog
    # and matches the L3 tab id on the frontend.
    section: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # IA output (validated against the agent's Pydantic schema before persist).
    ai_analysis: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ai_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Analyst overrides
    analyst_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyst_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    analyst_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analyst_approved_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    regenerated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    def __repr__(self) -> str:
        return f"<CreditDossierAnalysis section={self.section} dossier={self.dossier_id}>"
