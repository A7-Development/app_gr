"""CreditDossierFinancial — structured financial data extracted from documents.

Populated by the document_extractor agent (DRE + Balance Sheet rows) and
read by the financial_analyst agent. Indicators are derived (margin, ratios)
either by the agent or by the `calculate_metric` tool.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class CreditDossierFinancial(Base):
    """One period of structured financial statements for a company in the dossier."""

    __tablename__ = "credit_dossier_financial"

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

    cnpj: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    # ── DRE ──────────────────────────────────────────────────────────
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)
    cogs: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)
    gross_profit: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)
    operating_expenses: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)
    ebitda: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)
    financial_result: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)
    net_income: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)

    # ── Balance Sheet ───────────────────────────────────────────────
    total_assets: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)
    current_assets: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)
    total_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)
    current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)
    equity: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)

    # ── Derived indicators ──────────────────────────────────────────
    gross_margin_pct: Mapped[Decimal | None] = mapped_column(Numeric(precision=8, scale=4), nullable=True)
    ebitda_margin_pct: Mapped[Decimal | None] = mapped_column(Numeric(precision=8, scale=4), nullable=True)
    net_margin_pct: Mapped[Decimal | None] = mapped_column(Numeric(precision=8, scale=4), nullable=True)
    current_ratio: Mapped[Decimal | None] = mapped_column(Numeric(precision=8, scale=4), nullable=True)
    debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(precision=8, scale=4), nullable=True)

    # ── Provenance ──────────────────────────────────────────────────
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="self_declared")
    source_document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("credit_dossier_document.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<CreditDossierFinancial cnpj={self.cnpj} period={self.period_start}/{self.period_end}>"
