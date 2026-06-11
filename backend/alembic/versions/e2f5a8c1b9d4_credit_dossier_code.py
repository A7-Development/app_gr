"""credit_dossier.code — código humano único da análise (DC-AAAA-NNNN)

Referência de suporte/comunicação entre analista, gestor e suporte
("a DC-2026-0148 deu flag crítica") — o handoff Conceito D já exibia esse
formato na sidebar de etapas. UUID continua sendo a chave técnica.

- sequence global `credit_dossier_code_seq`
- coluna `code` (unique) em `credit_dossier`
- backfill dos dossiês existentes em ordem de criação, com o ANO da criação
  no código (numeração contínua, sem reset anual — colisão impossível)

Revision ID: e2f5a8c1b9d4
Revises: d8e1f3a9c5b7
Create Date: 2026-06-11
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2f5a8c1b9d4"
down_revision: str | None = "d8e1f3a9c5b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS credit_dossier_code_seq"))
    op.add_column(
        "credit_dossier", sa.Column("code", sa.String(length=16), nullable=True)
    )
    # Backfill em ordem de criação — numeração estável e cronológica.
    bind.execute(
        sa.text(
            """
            WITH ordenados AS (
                SELECT id,
                       EXTRACT(YEAR FROM created_at)::int AS ano,
                       nextval('credit_dossier_code_seq') AS seq
                FROM credit_dossier
                WHERE code IS NULL
                ORDER BY created_at
            )
            UPDATE credit_dossier d
            SET code = 'DC-' || o.ano || '-' || LPAD(o.seq::text, 4, '0')
            FROM ordenados o
            WHERE d.id = o.id
            """
        )
    )
    op.create_index(
        "ix_credit_dossier_code", "credit_dossier", ["code"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_credit_dossier_code", table_name="credit_dossier")
    op.drop_column("credit_dossier", "code")
    op.execute(sa.text("DROP SEQUENCE IF EXISTS credit_dossier_code_seq"))
