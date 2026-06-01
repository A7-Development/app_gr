"""wh_bitfin_entidade -- dim de entidades (cedentes) Bitfin

Resolve entidade_id -> nome/documento para os agregados do DRE
(receita por cedente). Populada pelo adapter (sync_bitfin_entidade) com o
subconjunto de Entidade referenciado pelo DemonstrativoDeResultado.

Revision ID: f3c8a1d6b9e2
Revises: e7b3f1c9a2d4
Create Date: 2026-05-31
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3c8a1d6b9e2"
down_revision: str | None = "e7b3f1c9a2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wh_bitfin_entidade",
        sa.Column(
            "id", sa.UUID(), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("entidade_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=200), nullable=False),
        sa.Column("documento", sa.String(length=20), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_by_version", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "entidade_id", name="uq_wh_bitfin_entidade"),
    )
    op.create_index(
        op.f("ix_wh_bitfin_entidade_tenant_id"),
        "wh_bitfin_entidade",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_wh_bitfin_entidade_tenant_id"), table_name="wh_bitfin_entidade"
    )
    op.drop_table("wh_bitfin_entidade")
