"""boleto_evento_titulo_id — espinha de identidade

Revision ID: a2c9f4e7b6d8
Revises: f8c3a1e6d4b9
Create Date: 2026-07-09

Bug de identidade (achado Ricardo 2026-07-09, cruzamento com Bitfin): o join
evento->titulo por `nosso_numero` COLIDE entre cedentes (Vortx reusa o
numero) e fabricava convergencia falsa de praca. Solucao: resolver o
`titulo_id` (Bitfin TituloId, ja em wh_titulo) por `numero_documento`, com
desempate por valor, e materializar no evento como identidade estavel.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a2c9f4e7b6d8"
down_revision: str | Sequence[str] | None = "f8c3a1e6d4b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("wh_boleto_evento", sa.Column("titulo_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_wh_boleto_evento_titulo_id",
        "wh_boleto_evento",
        ["tenant_id", "titulo_id"],
    )
    # Resolucao evento->titulo casa por (tenant, numero) — indice obrigatorio
    # (sem ele o backfill correlacionado faz seq scan por linha).
    op.create_index(
        "ix_wh_titulo_tenant_numero",
        "wh_titulo",
        ["tenant_id", "numero"],
    )


def downgrade() -> None:
    op.drop_index("ix_wh_titulo_tenant_numero", table_name="wh_titulo")
    op.drop_index("ix_wh_boleto_evento_titulo_id", table_name="wh_boleto_evento")
    op.drop_column("wh_boleto_evento", "titulo_id")
