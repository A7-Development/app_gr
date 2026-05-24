"""F1.C3: agent_session + agent_session_step (memoria de sessao persistente)

Revision ID: b8e2f4a91c7d
Revises: d95475d36c7c
Create Date: 2026-05-23 18:00:00.000000

Cria duas tabelas pra persistencia hibrida da AnalysisSession (CLAUDE.md
sec 19.11):

    agent_session       sumario de uma analise agentica
    agent_session_step  steps append-only (tool_use/result/error/...)

A camada `app/agentic/memory/persistence.py` (F1.C3) faz flush
assincrono quando a session vive > 60s OU em end_session().

Isolamento (CLAUDE.md sec 10): tenant_id NOT NULL em ambas + indices
compostos com tenant_id na frente. Toda query precisa filtrar antes.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "b8e2f4a91c7d"
down_revision = "d95475d36c7c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── agent_session ────────────────────────────────────────────────────
    op.create_table(
        "agent_session",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "started_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("context_label", sa.String(length=256), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scratchpad_final", sa.Text(), nullable=True),
        sa.Column(
            "step_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "ix_agent_session_tenant_started",
        "agent_session",
        ["tenant_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_agent_session_context_label",
        "agent_session",
        ["tenant_id", "context_label"],
    )

    # ─── agent_session_step ───────────────────────────────────────────────
    op.create_table(
        "agent_session_step",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_full_id", sa.String(length=128), nullable=True),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column(
            "iso_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "session_id", "step_index",
            name="uq_agent_session_step_session_index",
        ),
    )
    op.create_index(
        "ix_agent_session_step_tenant_iso",
        "agent_session_step",
        ["tenant_id", sa.text("iso_at DESC")],
    )
    op.create_index(
        "ix_agent_session_step_session",
        "agent_session_step",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_session_step_session", table_name="agent_session_step")
    op.drop_index(
        "ix_agent_session_step_tenant_iso", table_name="agent_session_step"
    )
    op.drop_table("agent_session_step")
    op.drop_index("ix_agent_session_context_label", table_name="agent_session")
    op.drop_index("ix_agent_session_tenant_started", table_name="agent_session")
    op.drop_table("agent_session")
