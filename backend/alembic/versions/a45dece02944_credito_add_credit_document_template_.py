"""credito: add credit_document_template (per-tenant doc extraction templates)

Revision ID: a45dece02944
Revises: cbe3af2c3bf5
Create Date: 2026-05-01 12:25:32.354303

Adds the `credit_document_template` table — per-tenant templates that guide
the document_extractor agent when processing uploaded documents. Each tenant
defines its own templates (ex: "Relatorio Onboard A7"); Strata-provided
templates use `tenant_id IS NULL` and any tenant can use or clone them.

Without a template selected at upload time, the document extractor runs in
free-form mode (extracts whatever appears relevant).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a45dece02944"
down_revision: str | None = "cbe3af2c3bf5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credit_document_template",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column(
            "doc_type",
            sa.Enum(
                "DRE", "BALANCE_SHEET", "REVENUE_REPORT", "INDEBTEDNESS", "SCR",
                "INCOME_TAX_PF", "CNH", "RG", "SOCIAL_CONTRACT", "COMMERCIAL_VISIT",
                "PHOTO", "ABC_CURVE", "PLEA_SOURCE", "OTHER",
                name="credit_document_type",
                native_enum=False,
                length=32,
                create_type=False,  # already exists from credit_dossier_document
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("fields_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_credit_document_template_doc_type"),
        "credit_document_template",
        ["doc_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_document_template_tenant_id"),
        "credit_document_template",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_credit_document_template_tenant_id"),
        table_name="credit_document_template",
    )
    op.drop_index(
        op.f("ix_credit_document_template_doc_type"),
        table_name="credit_document_template",
    )
    op.drop_table("credit_document_template")
