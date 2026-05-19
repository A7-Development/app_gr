"""identity: tenant lifecycle + user role + invitations

Revision ID: d7e3a9b1f4c2
Revises: e8a2b9c4d167
Create Date: 2026-05-18 21:00:00.000000

Onda 1 da gestao de tenants/users via UI (CLAUDE.md §12, anotacao
project_admin_gestao_tenants_users.md).

1. ALTER tenants: ADD status (enum: trial/active/suspended/cancelled), trial_ends_at.
   Backfill: existentes -> 'active'.
2. ALTER users:   ADD tenant_role (enum: owner/member/viewer), invited_by_id FK.
   Backfill: existentes -> 'owner' (sao users seed criados via SQL manual,
   sao Owners por definicao no modelo atual).
3. CREATE user_invitation table.

NOTE: SAEnum com `native_enum=False` armazena o NAME do enum em UPPERCASE
no banco (TRIAL, ACTIVE, OWNER, etc.), consistente com `module` e
`permission` existentes. Ver migration 855c33dfd7df pra explicacao.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7e3a9b1f4c2"
down_revision: str | None = "e8a2b9c4d167"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. tenants.status + trial_ends_at
    # ------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "status",
            sa.Enum(
                "TRIAL",
                "ACTIVE",
                "SUSPENDED",
                "CANCELLED",
                name="tenant_status",
                native_enum=False,
                length=16,
                create_constraint=False,
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_tenants_status"), "tenants", ["status"], unique=False)

    # ------------------------------------------------------------------
    # 2. users.tenant_role + invited_by_id
    # ------------------------------------------------------------------
    # 2a. Add column nullable with default OWNER (so backfill is implicit
    # for existing users — they are the seed Owners of their tenants).
    op.add_column(
        "users",
        sa.Column(
            "tenant_role",
            sa.Enum(
                "OWNER",
                "MEMBER",
                "VIEWER",
                name="tenant_role",
                native_enum=False,
                length=16,
                create_constraint=False,
            ),
            server_default="OWNER",
            nullable=False,
        ),
    )
    # 2b. After backfill, flip the default for new rows to MEMBER (safer
    # default for invited users — Owner must be explicit).
    op.alter_column("users", "tenant_role", server_default="MEMBER")

    op.add_column(
        "users",
        sa.Column("invited_by_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_invited_by_id",
        "users",
        "users",
        ["invited_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_users_tenant_role"), "users", ["tenant_role"], unique=False
    )

    # ------------------------------------------------------------------
    # 3. user_invitation
    # ------------------------------------------------------------------
    op.create_table(
        "user_invitation",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "OWNER",
                "MEMBER",
                "VIEWER",
                name="tenant_role",
                native_enum=False,
                length=16,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("invited_by_id", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["invited_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_user_invitation_token_hash"),
    )
    op.create_index(
        op.f("ix_user_invitation_tenant_id"),
        "user_invitation",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_invitation_email"),
        "user_invitation",
        ["email"],
        unique=False,
    )
    # Partial unique: only one OPEN (not accepted, not revoked) invitation
    # per (tenant, email). Accepted/revoked rows are kept for audit.
    op.execute(
        "CREATE UNIQUE INDEX uq_user_invitation_open "
        "ON user_invitation(tenant_id, email) "
        "WHERE accepted_at IS NULL AND revoked_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_user_invitation_open")
    op.drop_index(op.f("ix_user_invitation_email"), table_name="user_invitation")
    op.drop_index(op.f("ix_user_invitation_tenant_id"), table_name="user_invitation")
    op.drop_table("user_invitation")

    op.drop_index(op.f("ix_users_tenant_role"), table_name="users")
    op.drop_constraint("fk_users_invited_by_id", "users", type_="foreignkey")
    op.drop_column("users", "invited_by_id")
    op.drop_column("users", "tenant_role")

    op.drop_index(op.f("ix_tenants_status"), table_name="tenants")
    op.drop_column("tenants", "trial_ends_at")
    op.drop_column("tenants", "status")
