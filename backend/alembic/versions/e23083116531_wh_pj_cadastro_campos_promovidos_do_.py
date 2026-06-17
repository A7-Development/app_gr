"""wh_pj_cadastro: campos promovidos do basic_data

Revision ID: e23083116531
Revises: eb0551ae0d9a
Create Date: 2026-06-17 12:16:25.443669

Promove 12 campos do basic_data (BDC) para colunas da wh_pj_cadastro (selecao
Ricardo 2026-06-17): regime tributario, porte, natureza juridica, situacao
especial (RJ/falida), datas de situacao, e historico de mudanca de nome/regime.
Tudo nullable — backfill via re-fetch (bronze imutavel preserva o raw).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e23083116531'
down_revision: str | None = 'eb0551ae0d9a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLS = [
    ('regime_tributario', sa.String(length=64)),
    ('porte', sa.String(length=32)),
    ('optante_simples', sa.Boolean()),
    ('natureza_juridica_codigo', sa.String(length=16)),
    ('natureza_juridica', sa.String(length=128)),
    ('situacao_especial', sa.String(length=128)),
    ('situacao_cadastral_desde', sa.Date()),
    ('data_inicio_atividade', sa.Date()),
    ('origem_cadastral', sa.String(length=64)),
    ('mudou_nome', sa.Boolean()),
    ('mudou_regime', sa.Boolean()),
    ('historico_nomes', postgresql.JSONB(astext_type=sa.Text())),
]


def upgrade() -> None:
    for name, type_ in _COLS:
        op.add_column('wh_pj_cadastro', sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLS):
        op.drop_column('wh_pj_cadastro', name)
