"""warehouse: serasa_pj fix — month columns widen (FEBRUARY/MARCH no payload)

Revision ID: f3a8b9d2c1e4
Revises: f9c2a6e8b3d1
Create Date: 2026-05-01 23:50:00.000000

Bug descoberto com payload VALOREN: segmentData.{drawee,assignor}.
businessReferences.businessReferencesList[].monthPotentialDate vem como
texto longo ("FEBRUARY", "MARCH") em vez de numero ("4"). Mesmo padrao
em evolutionCommitmentsSuppliers.

Fix: ALTER colunas `reference_month` e `month_commitment` de VARCHAR(2)
pra VARCHAR(16) — aceita ambos formatos sem normalizacao.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a8b9d2c1e4"
down_revision: str | None = "f9c2a6e8b3d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "wh_serasa_pj_business_reference",
        "reference_month",
        existing_type=sa.String(length=2),
        type_=sa.String(length=16),
    )
    op.alter_column(
        "wh_serasa_pj_pagamento_evolucao_mensal",
        "month_commitment",
        existing_type=sa.String(length=2),
        type_=sa.String(length=16),
    )


def downgrade() -> None:
    op.alter_column(
        "wh_serasa_pj_pagamento_evolucao_mensal",
        "month_commitment",
        existing_type=sa.String(length=16),
        type_=sa.String(length=2),
    )
    op.alter_column(
        "wh_serasa_pj_business_reference",
        "reference_month",
        existing_type=sa.String(length=16),
        type_=sa.String(length=2),
    )
