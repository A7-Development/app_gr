"""workflow: add workflow_notification table

Revision ID: 7afc13ded02f
Revises: a45dece02944
Create Date: 2026-05-01 12:53:30.651529

Creates `workflow_notification` to record dispatched notifications during
workflow execution. Used by the new `notification` node type. MVP supports
channel `log`; `email` is recorded but not actually sent.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7afc13ded02f"
down_revision: str | None = "a45dece02944"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_notification",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("delivered", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_run.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_workflow_notification_run_id"),
        "workflow_notification",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_notification_tenant_id"),
        "workflow_notification",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_workflow_notification_tenant_id"),
        table_name="workflow_notification",
    )
    op.drop_index(
        op.f("ix_workflow_notification_run_id"),
        table_name="workflow_notification",
    )
    op.drop_table("workflow_notification")
