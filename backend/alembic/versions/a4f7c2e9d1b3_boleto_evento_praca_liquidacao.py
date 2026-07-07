"""wh_boleto_evento: praca de liquidacao (banco/agencia pagadora + data credito).

Fonte primaria antifraude (Sentinela CNAB): posicoes 166-168/169-173/296-301 do
retorno CNAB400, independentes do cadastro de agencias do ERP. Colunas nullable
(so liquidacoes carregam; backfill via scripts/reparse_cnab_ocorrencias.py +
scripts/backfill_boleto_evento.py).

Revision ID: a4f7c2e9d1b3
Revises: b2d7e4a8c1f5
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a4f7c2e9d1b3"
down_revision = "b2d7e4a8c1f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wh_boleto_evento",
        sa.Column("banco_pagador", sa.String(length=3), nullable=True),
    )
    op.add_column(
        "wh_boleto_evento",
        sa.Column("agencia_pagadora", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "wh_boleto_evento",
        sa.Column("data_credito", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wh_boleto_evento", "data_credito")
    op.drop_column("wh_boleto_evento", "agencia_pagadora")
    op.drop_column("wh_boleto_evento", "banco_pagador")
