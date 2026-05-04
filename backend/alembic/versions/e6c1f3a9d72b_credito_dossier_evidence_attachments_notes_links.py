"""credito: dossier evidence (attachments + step notes + step links)

Adds three tables that hold the rich evidence the analyst collects during
a credit dossier execution:

- `credit_dossier_attachment` — files uploaded by the analyst (DRE, balance,
  IR, photos, etc). Optionally pinned to a step via `node_id`. Blob lives
  on filesystem under `DOSSIER_STORAGE_ROOT`; row stores metadata + sha256
  for dedup.

- `credit_dossier_step_note` — markdown notes the analyst writes on a
  specific step of the workflow. `body_md` is bounded (1..10000 chars).
  `pinned=true` floats the note to the top of the right-rail Evidence list.

- `credit_dossier_step_link` — external URL references (online statements,
  client portals, third-party sites). Optionally pinned to a step.

All three carry `tenant_id` for multi-tenant isolation, FK to
`credit_dossier(id) ON DELETE CASCADE` (when the dossier dies, evidence
dies with it), and FK to `users(id) ON DELETE SET NULL` for authorship.

Revision ID: e6c1f3a9d72b
Revises: f4a8b7c2d6e9
Create Date: 2026-05-03 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6c1f3a9d72b"
down_revision: str | None = "f4a8b7c2d6e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─── credit_dossier_attachment ────────────────────────────────────────
    op.create_table(
        "credit_dossier_attachment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("dossier_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dossier_id"], ["credit_dossier.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_credit_dossier_attachment_tenant_id"),
        "credit_dossier_attachment",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_dossier_attachment_dossier_id"),
        "credit_dossier_attachment",
        ["dossier_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_dossier_attachment_node_id"),
        "credit_dossier_attachment",
        ["node_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_dossier_attachment_sha256"),
        "credit_dossier_attachment",
        ["sha256"],
        unique=False,
    )
    op.create_index(
        "ix_credit_dossier_attachment_tenant_dossier",
        "credit_dossier_attachment",
        ["tenant_id", "dossier_id"],
        unique=False,
    )
    op.create_index(
        "ix_credit_dossier_attachment_tenant_dossier_node",
        "credit_dossier_attachment",
        ["tenant_id", "dossier_id", "node_id"],
        unique=False,
    )

    # ─── credit_dossier_step_note ─────────────────────────────────────────
    op.create_table(
        "credit_dossier_step_note",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("dossier_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column(
            "pinned",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("author_id", sa.UUID(), nullable=True),
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
        sa.CheckConstraint(
            "char_length(body_md) BETWEEN 1 AND 10000",
            name="ck_dossier_step_note_body_md_length",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dossier_id"], ["credit_dossier.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_credit_dossier_step_note_tenant_id"),
        "credit_dossier_step_note",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_dossier_step_note_dossier_id"),
        "credit_dossier_step_note",
        ["dossier_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_dossier_step_note_node_id"),
        "credit_dossier_step_note",
        ["node_id"],
        unique=False,
    )
    op.create_index(
        "ix_credit_dossier_step_note_tenant_dossier_node",
        "credit_dossier_step_note",
        ["tenant_id", "dossier_id", "node_id"],
        unique=False,
    )

    # ─── credit_dossier_step_link ─────────────────────────────────────────
    op.create_table(
        "credit_dossier_step_link",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("dossier_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("added_by", sa.UUID(), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dossier_id"], ["credit_dossier.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_credit_dossier_step_link_tenant_id"),
        "credit_dossier_step_link",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_dossier_step_link_dossier_id"),
        "credit_dossier_step_link",
        ["dossier_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credit_dossier_step_link_node_id"),
        "credit_dossier_step_link",
        ["node_id"],
        unique=False,
    )
    op.create_index(
        "ix_credit_dossier_step_link_tenant_dossier_node",
        "credit_dossier_step_link",
        ["tenant_id", "dossier_id", "node_id"],
        unique=False,
    )


def downgrade() -> None:
    # links
    op.drop_index(
        "ix_credit_dossier_step_link_tenant_dossier_node",
        table_name="credit_dossier_step_link",
    )
    op.drop_index(
        op.f("ix_credit_dossier_step_link_node_id"),
        table_name="credit_dossier_step_link",
    )
    op.drop_index(
        op.f("ix_credit_dossier_step_link_dossier_id"),
        table_name="credit_dossier_step_link",
    )
    op.drop_index(
        op.f("ix_credit_dossier_step_link_tenant_id"),
        table_name="credit_dossier_step_link",
    )
    op.drop_table("credit_dossier_step_link")

    # notes
    op.drop_index(
        "ix_credit_dossier_step_note_tenant_dossier_node",
        table_name="credit_dossier_step_note",
    )
    op.drop_index(
        op.f("ix_credit_dossier_step_note_node_id"),
        table_name="credit_dossier_step_note",
    )
    op.drop_index(
        op.f("ix_credit_dossier_step_note_dossier_id"),
        table_name="credit_dossier_step_note",
    )
    op.drop_index(
        op.f("ix_credit_dossier_step_note_tenant_id"),
        table_name="credit_dossier_step_note",
    )
    op.drop_table("credit_dossier_step_note")

    # attachments
    op.drop_index(
        "ix_credit_dossier_attachment_tenant_dossier_node",
        table_name="credit_dossier_attachment",
    )
    op.drop_index(
        "ix_credit_dossier_attachment_tenant_dossier",
        table_name="credit_dossier_attachment",
    )
    op.drop_index(
        op.f("ix_credit_dossier_attachment_sha256"),
        table_name="credit_dossier_attachment",
    )
    op.drop_index(
        op.f("ix_credit_dossier_attachment_node_id"),
        table_name="credit_dossier_attachment",
    )
    op.drop_index(
        op.f("ix_credit_dossier_attachment_dossier_id"),
        table_name="credit_dossier_attachment",
    )
    op.drop_index(
        op.f("ix_credit_dossier_attachment_tenant_id"),
        table_name="credit_dossier_attachment",
    )
    op.drop_table("credit_dossier_attachment")
