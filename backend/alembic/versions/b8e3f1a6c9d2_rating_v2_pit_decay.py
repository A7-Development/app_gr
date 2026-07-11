"""rating_v2_pit_decay

Revision ID: b8e3f1a6c9d2
Revises: a5d8e2c7f1b4
Create Date: 2026-07-11

Rating v2 POINT-IN-TIME (decisao Ricardo 2026-07-11 apos pesquisa de mercado):
troca a analise-plana-12m por decaimento exponencial de recencia (half-life
90d) + camada de watchlist (early-warning) separada. Dois parametros novos
na deteccao_parametro (versionados).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b8e3f1a6c9d2"
down_revision: str | Sequence[str] | None = "a5d8e2c7f1b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    params = sa.table(
        "deteccao_parametro",
        sa.column("nome", sa.String),
        sa.column("valor", postgresql.JSONB),
        sa.column("version", sa.Integer),
        sa.column("motivo", sa.String),
        sa.column("criado_por", sa.String),
    )
    motivo = "seed b8e3f1a6c9d2 — rating v2 PiT (half-life 90d + watchlist)"
    op.bulk_insert(
        params,
        [
            {"nome": "rating_half_life_dias", "valor": 90, "version": 1,
             "motivo": motivo, "criado_por": "migration"},
            {"nome": "rating_watchlist_dias", "valor": 90, "version": 1,
             "motivo": motivo, "criado_por": "migration"},
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM deteccao_parametro "
        "WHERE nome IN ('rating_half_life_dias', 'rating_watchlist_dias') "
        "AND version = 1"
    )
