"""warehouse: wh_dim_dia_util + cedente em wh_operacao

Cria a dimensao de calendario `wh_dim_dia_util` e adiciona `cedente_id` +
`cedente_nome` (nullable, desnormalizado) em `wh_operacao`. Habilita as
analises da L2 Operacoes2:

- Ritmo do mes corrente (vs mesmo nº de DUs do mes anterior)
- Pace diario (VOP / DU corridos)
- Heatmap dow x semana do mes
- Top cedentes em receita / ranking de concentracao por cedente

Populacao:
- `wh_dim_dia_util`: rodar `python -m backend.scripts.populate_dia_util` apos
  apply (le `Bitfin.VW_FERIADOS_NACIONAL` + gera datas 2019-2030).
- `wh_operacao.cedente_id` / `cedente_nome`: re-rodar ETL do bitfin com mapper
  estendido (followup separado — colunas ficam NULL ate la).

Revision ID: f4a8b7c2d6e9
Revises: c31e8ab2b766
Create Date: 2026-05-03 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4a8b7c2d6e9'
down_revision: str | None = 'c31e8ab2b766'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) wh_dim_dia_util — calendario diario com flag DU + indices precomputados
    op.create_table(
        'wh_dim_dia_util',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('dia_da_semana', sa.Integer(), nullable=False),
        sa.Column('dia_da_semana_nome', sa.String(length=20), nullable=False),
        sa.Column('eh_fim_de_semana', sa.Boolean(), nullable=False),
        sa.Column('eh_feriado_nacional', sa.Boolean(), nullable=False),
        sa.Column('eh_dia_util', sa.Boolean(), nullable=False),
        sa.Column('dia_util_index_no_mes', sa.Integer(), nullable=True),
        sa.Column('total_dias_uteis_no_mes', sa.Integer(), nullable=False),
        sa.Column('semana_do_mes', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(length=64), nullable=False, server_default='DERIVED'),
        sa.Column(
            'ingested_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('ingested_by_version', sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'data', name='uq_wh_dim_dia_util'),
    )
    op.create_index(
        op.f('ix_wh_dim_dia_util_data'), 'wh_dim_dia_util', ['data'], unique=False
    )
    op.create_index(
        op.f('ix_wh_dim_dia_util_eh_dia_util'),
        'wh_dim_dia_util',
        ['eh_dia_util'],
        unique=False,
    )
    op.create_index(
        op.f('ix_wh_dim_dia_util_eh_feriado_nacional'),
        'wh_dim_dia_util',
        ['eh_feriado_nacional'],
        unique=False,
    )
    op.create_index(
        op.f('ix_wh_dim_dia_util_tenant_id'),
        'wh_dim_dia_util',
        ['tenant_id'],
        unique=False,
    )
    # Indice composto para query "DU index do dia X" (filtra DU e ordena por data).
    op.create_index(
        'ix_wh_dim_dia_util_tenant_data_du',
        'wh_dim_dia_util',
        ['tenant_id', 'data', 'eh_dia_util'],
        unique=False,
    )

    # 2) wh_operacao — colunas desnormalizadas de cedente
    op.add_column('wh_operacao', sa.Column('cedente_id', sa.Integer(), nullable=True))
    op.add_column(
        'wh_operacao', sa.Column('cedente_nome', sa.String(length=200), nullable=True)
    )
    op.create_index(
        op.f('ix_wh_operacao_cedente_id'), 'wh_operacao', ['cedente_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_wh_operacao_cedente_id'), table_name='wh_operacao')
    op.drop_column('wh_operacao', 'cedente_nome')
    op.drop_column('wh_operacao', 'cedente_id')

    op.drop_index('ix_wh_dim_dia_util_tenant_data_du', table_name='wh_dim_dia_util')
    op.drop_index(op.f('ix_wh_dim_dia_util_tenant_id'), table_name='wh_dim_dia_util')
    op.drop_index(
        op.f('ix_wh_dim_dia_util_eh_feriado_nacional'), table_name='wh_dim_dia_util'
    )
    op.drop_index(op.f('ix_wh_dim_dia_util_eh_dia_util'), table_name='wh_dim_dia_util')
    op.drop_index(op.f('ix_wh_dim_dia_util_data'), table_name='wh_dim_dia_util')
    op.drop_table('wh_dim_dia_util')
