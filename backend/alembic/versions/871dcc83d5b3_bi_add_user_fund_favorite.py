"""bi: add user_fund_favorite

Revision ID: 871dcc83d5b3
Revises: e85185ac4d1e
Create Date: 2026-04-22 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "871dcc83d5b3"
down_revision: str | None = "e85185ac4d1e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_fund_favorite",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("cnpj", sa.String(length=14), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "cnpj", name="pk_user_fund_favorite"),
    )
    op.create_index(
        "ix_user_fund_favorite_tenant_user",
        "user_fund_favorite",
        ["tenant_id", "user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_fund_favorite_tenant_user", table_name="user_fund_favorite"
    )
    op.drop_table("user_fund_favorite")
