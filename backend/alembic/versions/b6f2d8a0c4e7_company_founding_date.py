"""credit_dossier_company -- founding_date (idade da empresa)

Data de fundacao/constituicao da empresa. Insumo do gate de elegibilidade
(check company_founding_age: idade > N anos). Na Fatia 1 vem auto-declarada
do cadastro; depois a Receita valida/cruza (familia cross-fonte).

Revision ID: b6f2d8a0c4e7
Revises: c4e8b2d6f0a3
Create Date: 2026-06-01
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b6f2d8a0c4e7"
down_revision: str | None = "c4e8b2d6f0a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "credit_dossier_company",
        sa.Column("founding_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("credit_dossier_company", "founding_date")
