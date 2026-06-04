"""credit_dossier_company: cadastral silver (tax_status, cnaes, capital_social)

Colunas silver lidas pelos checks do gate A2 (company_status_active,
cnae_permitido) e pelo cross-check de capital. Populadas pelo adapter cadastral
BDC (Companies/BASIC_DATA_V1). Aditivas e nullable — zero risco em prod.

Revision ID: d4f1a8c3b7e2
Revises: f9a2c7e1b4d6
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "d4f1a8c3b7e2"
down_revision: str | None = "f9a2c7e1b4d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "credit_dossier_company",
        sa.Column("tax_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "credit_dossier_company",
        sa.Column("cnaes", JSONB(), nullable=True),
    )
    op.add_column(
        "credit_dossier_company",
        sa.Column("capital_social", sa.Numeric(precision=18, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("credit_dossier_company", "capital_social")
    op.drop_column("credit_dossier_company", "cnaes")
    op.drop_column("credit_dossier_company", "tax_status")
