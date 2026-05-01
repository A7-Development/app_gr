"""CreditDossier — root entity of the credit analysis module.

A dossier is bound 1-1 to a `WorkflowRun` from the workflow engine. The
engine drives execution; the dossier owns the domain data (companies,
people, documents, analyses, opinion).

Lifecycle (`status`, see `DossierStatus`):
    DRAFT       — created, workflow not started
    COLLECTING  — bureau queries running, docs being uploaded
    ANALYZING   — specialist agents executing
    REVIEW      — workflow paused on human_review
    FINALIZED   — opinion signed, output PDF generated
    CANCELLED   — dossier or workflow cancelled by user

Multi-tenant: every query MUST scope by `tenant_id`.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import DossierStatus


class CreditDossier(Base):
    """The root container of one credit analysis."""

    __tablename__ = "credit_dossier"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Domain identity
    target_cnpj: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Pleito (high-level summary; full structured pleito in `credit_dossier_pleito`)
    operation_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True
    )
    requested_term_days: Mapped[int | None] = mapped_column(nullable=True)

    # Lifecycle
    status: Mapped[DossierStatus] = mapped_column(
        SAEnum(
            DossierStatus,
            name="dossier_status",
            native_enum=False,
            length=32,
        ),
        nullable=False,
        default=DossierStatus.DRAFT,
        index=True,
    )

    # Workflow binding (1-1 with WorkflowRun)
    workflow_definition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_definition.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workflow_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_run.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    # Ownership
    analyst_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Audit
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<CreditDossier id={self.id} cnpj={self.target_cnpj} status={self.status.value}>"
