"""widen serasa_pj percentage columns to NUMERIC(9,4)

A Serasa envia percentuais em centesimos (basis points): 100% = 10000. As
colunas de percentual estavam dimensionadas para < 10000 (Numeric(8,4)/(7,4)),
estourando NumericValueOutOfRangeError no bucket PONTUAL de empresas 100%
pontuais (percentageTo=10000.0). Alarga as 4 colunas para Numeric(9,4)
(max 99999.9999), que segura 10000.0000 e preserva o scale.

Confirmado via REALINVEST/Bitfin completeness check (NUTRATEC 07902623000107).

Revision ID: a1b2c3d4e5f6
Revises: d1e5b2c4a7f9
Create Date: 2026-05-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "d1e5b2c4a7f9"
branch_labels = None
depends_on = None

# (tabela, coluna, tipo_antigo)
_WIDEN = [
    ("wh_serasa_pj_pagamento_bucket", "percentage_from", sa.Numeric(8, 4)),
    ("wh_serasa_pj_pagamento_bucket", "percentage_to", sa.Numeric(8, 4)),
    ("wh_serasa_pj_participacao", "percentual", sa.Numeric(7, 4)),
    ("wh_serasa_pj_socio", "percentual", sa.Numeric(7, 4)),
]


def upgrade() -> None:
    for table, col, old_type in _WIDEN:
        op.alter_column(
            table,
            col,
            type_=sa.Numeric(9, 4),
            existing_type=old_type,
            existing_nullable=True,
        )


def downgrade() -> None:
    # Pode falhar se ja houver valor >= 10000 gravado (esperado p/ buckets PONTUAL).
    for table, col, old_type in _WIDEN:
        op.alter_column(
            table,
            col,
            type_=old_type,
            existing_type=sa.Numeric(9, 4),
            existing_nullable=True,
        )
