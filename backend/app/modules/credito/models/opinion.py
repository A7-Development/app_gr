"""CreditDossierOpinion — final opinion / parecer for the credit committee."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import OpinionRecommendation


class CreditDossierOpinion(Base):
    """The final opinion record. Multiple versions per dossier (only one current)."""

    __tablename__ = "credit_dossier_opinion"

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

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Content
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    strengths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    concerns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    recommendation: Mapped[OpinionRecommendation] = mapped_column(
        SAEnum(
            OpinionRecommendation,
            name="opinion_recommendation",
            native_enum=False,
            length=24,
        ),
        nullable=False,
    )
    conditions: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Drafting trail
    ai_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyst_final: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Signature
    signed_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<CreditDossierOpinion v{self.version} dossier={self.dossier_id} "
            f"rec={self.recommendation.value}>"
        )

    @property
    def rationale(self) -> str | None:
        """Backwards-compatibility shim — callers expect `.rationale`."""
        return self.analyst_final or self.ai_draft
