"""decision_log.rule_or_model_version: VARCHAR(64) -> VARCHAR(255)

Revision ID: c7e4b2a8d5f1
Revises: a9d3e6f1b8c2
Create Date: 2026-07-23

CLAUDE.md §19.12: `decision_log.rule_or_model_version` carrega a string
composta do agente resolvido (`adapter+agente@v+persona@v+expertises@v+
prompt@v` — `ResolvedAgent.audit_version`). Com persona + prompt o
composto passa de 64 chars (ex.: o do Strata AI tem 95) e o INSERT
estourava StringDataRightTruncationError. Widening de varchar e
metadata-only no Postgres (sem rewrite da tabela append-only).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c7e4b2a8d5f1"
down_revision = "a9d3e6f1b8c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "decision_log",
        "rule_or_model_version",
        type_=sa.String(length=255),
        existing_type=sa.String(length=64),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Truncaria valores > 64 — downgrade so e seguro se nenhum composto
    # longo tiver sido gravado.
    op.alter_column(
        "decision_log",
        "rule_or_model_version",
        type_=sa.String(length=64),
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
