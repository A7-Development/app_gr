"""credit_policy + credit_policy_active -- politica de elegibilidade por tenant

Primitivo que o gate de elegibilidade (deterministic_check) referencia.
Versionada e imutavel por (tenant_id, name, version); ponteiro de versao ativa
em credit_policy_active (rollback de 1 click sem deploy), espelhando
ai_prompt / ai_prompt_active. Ver CLAUDE.md handoff esteira-credito §8 + §10.

Revision ID: e9c3a7d1f5b2
Revises: f3c8a1d6b9e2
Create Date: 2026-06-01
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e9c3a7d1f5b2"
down_revision: str | None = "f3c8a1d6b9e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credit_policy",
        sa.Column(
            "id", sa.UUID(), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column(
            "forbidden_cnae",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("min_capital_social", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("min_company_age_years", sa.Integer(), nullable=True),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "name", "version", name="uq_credit_policy_tenant_name_version"
        ),
    )
    op.create_index(
        op.f("ix_credit_policy_tenant_id"),
        "credit_policy",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "credit_policy_active",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("active_version", sa.String(length=32), nullable=False),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("changed_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("tenant_id", "name"),
    )


def downgrade() -> None:
    op.drop_table("credit_policy_active")
    op.drop_index(op.f("ix_credit_policy_tenant_id"), table_name="credit_policy")
    op.drop_table("credit_policy")
