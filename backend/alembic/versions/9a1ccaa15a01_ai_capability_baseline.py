"""ai capability baseline: 9 tables + tenants.is_system_maintainer

Revision ID: 9a1ccaa15a01
Revises: fcbb844bbdb8
Create Date: 2026-04-30 10:00:00.000000

Sub-fase 1.A do plano IA-as-a-Service:
- ALTER tenants ADD COLUMN is_system_maintainer (partial unique index garante <=1 row)
- CREATE ai_provider_credential (global, sem tenant_id)
- CREATE tenant_ai_subscription, user_ai_permission
- CREATE ai_usage_event, ai_credit_balance
- CREATE ai_conversation, ai_message, ai_conversation_summary
- CREATE ai_prompt_active
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a1ccaa15a01"
down_revision: str | None = "fcbb844bbdb8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Enum reuse (already exists in DB as varchar + CHECK constraints, native_enum=False).
# We pass create_type=False / use String when reusing to avoid CHECK constraint drift.
_module_enum = sa.Enum(
    "BI",
    "CADASTROS",
    "OPERACOES",
    "CREDITO",
    "CONTROLADORIA",
    "RISCO",
    "INTEGRACOES",
    "LABORATORIO",
    "ADMIN",
    name="module",
    native_enum=False,
    length=32,
    create_constraint=False,
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. tenants.is_system_maintainer
    # ------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "is_system_maintainer",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    # Partial unique index: at most one tenant marked as system maintainer.
    op.execute(
        "CREATE UNIQUE INDEX uq_only_one_system_maintainer "
        "ON tenants(is_system_maintainer) WHERE is_system_maintainer = true"
    )

    # ------------------------------------------------------------------
    # 2. ai_provider_credential (GLOBAL — no tenant_id)
    # ------------------------------------------------------------------
    op.create_table(
        "ai_provider_credential",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "provider",
            sa.Enum("OPENAI", "ANTHROPIC", name="ai_provider", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("alias", sa.String(length=64), nullable=False),
        sa.Column("encrypted_key", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("zdr_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_by", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["rotated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias", name="uq_ai_provider_credential_alias"),
    )
    op.create_index(
        op.f("ix_ai_provider_credential_active"),
        "ai_provider_credential",
        ["active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_provider_credential_provider"),
        "ai_provider_credential",
        ["provider"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 3. tenant_ai_subscription
    # ------------------------------------------------------------------
    op.create_table(
        "tenant_ai_subscription",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("plan_ref", sa.String(length=64), nullable=True),
        sa.Column(
            "monthly_credit_quota", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("hard_cap_brl", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("enabled_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled_until", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.create_index(
        op.f("ix_tenant_ai_subscription_enabled"),
        "tenant_ai_subscription",
        ["enabled"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 4. user_ai_permission
    # ------------------------------------------------------------------
    op.create_table(
        "user_ai_permission",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "permission",
            sa.Enum(
                "NONE",
                "READ",
                "WRITE",
                "ADMIN",
                name="ai_capability",
                native_enum=False,
                length=16,
            ),
            server_default="none",
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    # ------------------------------------------------------------------
    # 5. ai_usage_event (append-only, will be partitioned in Phase 2)
    # ------------------------------------------------------------------
    op.create_table(
        "ai_usage_event",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("feature", sa.String(length=64), nullable=False),
        sa.Column("context_module", _module_enum, nullable=True),
        sa.Column(
            "provider",
            sa.Enum(
                "OPENAI",
                "ANTHROPIC",
                name="ai_provider",
                native_enum=False,
                length=32,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("prompt_template_version", sa.String(length=64), nullable=True),
        sa.Column("tokens_input", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_output", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_cached", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "cost_brl_provider",
            sa.Numeric(precision=12, scale=6),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "cost_credits_billed", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum(
                "OK",
                "RATE_LIMITED",
                "ERROR",
                "OVER_BUDGET",
                "INJECTION_BLOCKED",
                name="ai_usage_status",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("decision_log_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decision_log_id"], ["decision_log.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_ai_usage_event_request_id"),
    )
    op.create_index(
        op.f("ix_ai_usage_event_tenant_id"), "ai_usage_event", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_ai_usage_event_occurred_at"), "ai_usage_event", ["occurred_at"], unique=False
    )
    # Composite index for billing rollups (most common access pattern).
    op.create_index(
        "ix_ai_usage_event_tenant_occurred_feature",
        "ai_usage_event",
        ["tenant_id", sa.text("occurred_at DESC"), "feature"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 6. ai_credit_balance
    # ------------------------------------------------------------------
    op.create_table(
        "ai_credit_balance",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("period_yyyymm", sa.String(length=7), nullable=False),
        sa.Column("granted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("consumed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("carryover", sa.Integer(), server_default="0", nullable=False),
        sa.Column("topup", sa.Integer(), server_default="0", nullable=False),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "period_yyyymm"),
    )

    # ------------------------------------------------------------------
    # 7. ai_conversation
    # ------------------------------------------------------------------
    op.create_table(
        "ai_conversation",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("page_context", sa.String(length=255), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_msg_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("turn_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_conversation_tenant_id"), "ai_conversation", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_ai_conversation_user_id"), "ai_conversation", ["user_id"], unique=False
    )

    # ------------------------------------------------------------------
    # 8. ai_message (will be partitioned in Phase 2)
    # ------------------------------------------------------------------
    op.create_table(
        "ai_message",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("USER", "AI", name="ai_message_role", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("text_redacted", sa.Text(), nullable=False),
        sa.Column("text_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("usage_event_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["ai_conversation.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["usage_event_id"], ["ai_usage_event.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_message_conversation_id"), "ai_message", ["conversation_id"], unique=False
    )
    # Unique to prevent double-write of the same turn under a retry.
    op.create_index(
        "uq_ai_message_conv_turn",
        "ai_message",
        ["conversation_id", "turn_index", "role"],
        unique=True,
    )

    # ------------------------------------------------------------------
    # 9. ai_conversation_summary
    # ------------------------------------------------------------------
    op.create_table(
        "ai_conversation_summary",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("up_to_turn", sa.Integer(), nullable=False),
        sa.Column("summary_text_redacted", sa.Text(), nullable=False),
        sa.Column("summary_text_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("generated_by_prompt_version", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["ai_conversation.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("conversation_id"),
    )

    # ------------------------------------------------------------------
    # 10. ai_prompt_active
    # ------------------------------------------------------------------
    op.create_table(
        "ai_prompt_active",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("active_version", sa.String(length=32), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("changed_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("ai_prompt_active")
    op.drop_table("ai_conversation_summary")
    op.drop_index("uq_ai_message_conv_turn", table_name="ai_message")
    op.drop_index(op.f("ix_ai_message_conversation_id"), table_name="ai_message")
    op.drop_table("ai_message")
    op.drop_index(op.f("ix_ai_conversation_user_id"), table_name="ai_conversation")
    op.drop_index(op.f("ix_ai_conversation_tenant_id"), table_name="ai_conversation")
    op.drop_table("ai_conversation")
    op.drop_table("ai_credit_balance")
    op.drop_index("ix_ai_usage_event_tenant_occurred_feature", table_name="ai_usage_event")
    op.drop_index(op.f("ix_ai_usage_event_occurred_at"), table_name="ai_usage_event")
    op.drop_index(op.f("ix_ai_usage_event_tenant_id"), table_name="ai_usage_event")
    op.drop_table("ai_usage_event")
    op.drop_table("user_ai_permission")
    op.drop_index(
        op.f("ix_tenant_ai_subscription_enabled"), table_name="tenant_ai_subscription"
    )
    op.drop_table("tenant_ai_subscription")
    op.drop_index(
        op.f("ix_ai_provider_credential_provider"), table_name="ai_provider_credential"
    )
    op.drop_index(
        op.f("ix_ai_provider_credential_active"), table_name="ai_provider_credential"
    )
    op.drop_table("ai_provider_credential")
    op.execute("DROP INDEX IF EXISTS uq_only_one_system_maintainer")
    op.drop_column("tenants", "is_system_maintainer")
