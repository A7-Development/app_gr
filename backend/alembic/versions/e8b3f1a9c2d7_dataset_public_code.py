"""provedor_dados_dataset: public_code (white-label neutro p/ tenant)

Codigo neutro definido pelo mantenedor, exposto ao tenant no lugar do vendor
(decisao 2026-06-04, opcao A). Aditiva nullable + unique. O tenant-facing nunca
ve provider_slug/provider_dataset_code — so public_code + display_name.

Revision ID: e8b3f1a9c2d7
Revises: d4f1a8c3b7e2
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8b3f1a9c2d7"
down_revision: str | None = "d4f1a8c3b7e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provedor_dados_dataset",
        sa.Column("public_code", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_provedor_dados_dataset_public_code",
        "provedor_dados_dataset",
        ["public_code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provedor_dados_dataset_public_code",
        table_name="provedor_dados_dataset",
    )
    op.drop_column("provedor_dados_dataset", "public_code")
