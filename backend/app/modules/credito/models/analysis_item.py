"""CreditAnalysisItem + CreditDossierCheck — checklist matrix.

`credit_analysis_item` defines the checklist structure (per tenant or global).
Items are referenced by code (e.g. SOC.001) and grouped by section.
Will be seeded once Ricardo shares the A7 checklist (2026-05-01).

`credit_dossier_check` records the evaluation of each item for a specific
dossier — both AI evaluation and analyst override.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import CheckSeverity, CheckStatus


class CreditAnalysisItem(Base):
    """Definition of a checklist item (one entry in the analysis matrix)."""

    __tablename__ = "credit_analysis_item"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # NULL tenant_id = template Strata; non-null = customized by tenant.
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    section: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    guidance: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Orientacao para o analista/IA sobre como avaliar"
    )

    severity: Mapped[CheckSeverity] = mapped_column(
        SAEnum(
            CheckSeverity,
            name="credit_check_severity",
            native_enum=False,
            length=16,
        ),
        nullable=False,
    )

    auto_evaluable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true",
        comment="Se True, IA avalia automaticamente; se False, exige analista",
    )

    order_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<CreditAnalysisItem code={self.code} section={self.section}>"


class CreditDossierCheck(Base):
    """Evaluation of one analysis item for a specific dossier."""

    __tablename__ = "credit_dossier_check"

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
    analysis_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("credit_analysis_item.id", ondelete="CASCADE"),
        nullable=False,
    )

    # AI evaluation
    ai_status: Mapped[CheckStatus | None] = mapped_column(
        SAEnum(
            CheckStatus,
            name="credit_check_status",
            native_enum=False,
            length=24,
        ),
        nullable=True,
    )
    ai_evaluation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=3), nullable=True)
    ai_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Analyst override
    analyst_status: Mapped[CheckStatus | None] = mapped_column(
        SAEnum(
            CheckStatus,
            name="credit_check_status",
            native_enum=False,
            length=24,
            create_type=False,
        ),
        nullable=True,
    )
    analyst_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyst_overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analyst_overridden_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Evidence: list of {type, ref} pointing to documents, queries, etc.
    evidence_refs: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<CreditDossierCheck item={self.analysis_item_id} ai={self.ai_status}>"
