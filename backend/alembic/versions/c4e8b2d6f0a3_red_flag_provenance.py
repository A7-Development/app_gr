"""credit_dossier_red_flag -- proveniencia estruturada da flag de cruzamento

Adiciona check_type (indexado), provenance (JSONB com a forma canonica:
source/field/expected/actual/comparisons) e decision_log_id (link de
auditoria). A flag de cruzamento com proveniencia rastreavel e a
unidade-produto da esteira. Ver CLAUDE.md handoff esteira-credito §1 + §14.

Revision ID: c4e8b2d6f0a3
Revises: e9c3a7d1f5b2
Create Date: 2026-06-01
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c4e8b2d6f0a3"
down_revision: str | None = "e9c3a7d1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "credit_dossier_red_flag",
        sa.Column("check_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "credit_dossier_red_flag",
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "credit_dossier_red_flag",
        sa.Column("decision_log_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        op.f("ix_credit_dossier_red_flag_check_type"),
        "credit_dossier_red_flag",
        ["check_type"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_credit_dossier_red_flag_decision_log",
        "credit_dossier_red_flag",
        "decision_log",
        ["decision_log_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_credit_dossier_red_flag_decision_log",
        "credit_dossier_red_flag",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_credit_dossier_red_flag_check_type"),
        table_name="credit_dossier_red_flag",
    )
    op.drop_column("credit_dossier_red_flag", "decision_log_id")
    op.drop_column("credit_dossier_red_flag", "provenance")
    op.drop_column("credit_dossier_red_flag", "check_type")
