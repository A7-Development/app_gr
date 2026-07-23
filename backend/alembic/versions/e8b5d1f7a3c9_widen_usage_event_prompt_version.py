"""ai_usage_event.prompt_template_version: VARCHAR(64) -> VARCHAR(255)

Revision ID: e8b5d1f7a3c9
Revises: c7e4b2a8d5f1
Create Date: 2026-07-23

Mesmo motivo de c7e4b2a8d5f1: turnos de agente resolvido gravam a string
composta `agente@v+persona@v+expertises@v+prompt@v` (CLAUDE.md §19.12),
que passa de 64 chars. Widening metadata-only.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "e8b5d1f7a3c9"
down_revision = "c7e4b2a8d5f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "ai_usage_event",
        "prompt_template_version",
        type_=sa.String(length=255),
        existing_type=sa.String(length=64),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "ai_usage_event",
        "prompt_template_version",
        type_=sa.String(length=64),
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
