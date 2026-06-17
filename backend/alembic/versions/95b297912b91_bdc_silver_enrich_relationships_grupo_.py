"""bdc silver enrich: relationships+grupo+kyc cols + wh_pj_evolucao

Revision ID: 95b297912b91
Revises: e23083116531
Create Date: 2026-06-17 13:29:04.354552

Auditoria raw->silver (Ricardo 2026-06-17): promove campos de relationships,
economic_group e kyc; cria o silver do dataset novo company_evolution
(header + serie mensal). Hand-written.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '95b297912b91'
down_revision: str | None = 'e23083116531'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_TYPE = sa.Enum(
    'ERP_BITFIN', 'ADMIN_QITECH', 'BUREAU_SERASA_PJ', 'BUREAU_SERASA_PF',
    'BUREAU_SCR_BACEN', 'BUREAU_BDC', 'DOCUMENT_NFE', 'COBRANCA',
    'COBRANCA_BRADESCO', 'COBRANCA_ITAU', 'COBRANCA_BMP', 'COBRANCA_VORTX',
    'SELF_DECLARED', 'PEER_DECLARED', 'INTERNAL_NOTE', 'DERIVED',
    name='source_type', native_enum=False, length=64,
)
_TRUST_LEVEL = sa.Enum(
    'HIGH', 'MEDIUM', 'LOW', name='trust_level', native_enum=False, length=16,
)


def _auditable() -> list:
    return [
        sa.Column('source_type', _SOURCE_TYPE, nullable=False),
        sa.Column('source_id', sa.String(length=255), nullable=False),
        sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('hash_origem', sa.String(length=64), nullable=True),
        sa.Column('ingested_by_version', sa.String(length=128), nullable=False),
        sa.Column('trust_level', _TRUST_LEVEL, nullable=False),
        sa.Column('collected_by', sa.UUID(), nullable=True),
    ]


def _fks() -> list:
    return [
        sa.ForeignKeyConstraint(['raw_id'], ['wh_bdc_raw_consulta.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['unidade_administrativa_id'], ['cadastros_unidade_administrativa.id'], ondelete='RESTRICT'),
    ]


def _lineage_indexes(table: str) -> None:
    for col in ('cnpj', 'raw_id', 'source_id', 'source_type', 'tenant_id', 'unidade_administrativa_id'):
        op.create_index(op.f(f'ix_{table}_{col}'), table, [col], unique=False)


def upgrade() -> None:
    # relationships -> wh_pj_cadastro
    op.add_column('wh_pj_cadastro', sa.Column('qtd_socios', sa.Integer(), nullable=True))
    op.add_column('wh_pj_cadastro', sa.Column('qtd_empresas_possuidas', sa.Integer(), nullable=True))
    op.add_column('wh_pj_cadastro', sa.Column('empresa_familiar', sa.Boolean(), nullable=True))
    op.add_column('wh_pj_cadastro', sa.Column('operada_pela_familia', sa.Boolean(), nullable=True))

    # economic_group -> wh_pj_grupo_indicador
    for col in (
        'faturamento_faixa', 'faturamento_faixa_min', 'faturamento_faixa_max',
        'faturamento_faixa_media', 'funcionarios_faixa', 'funcionarios_faixa_min',
        'funcionarios_faixa_max', 'funcionarios_faixa_media',
    ):
        op.add_column('wh_pj_grupo_indicador', sa.Column(col, sa.String(length=48), nullable=True))
    op.add_column('wh_pj_grupo_indicador', sa.Column('cnaes', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # kyc -> wh_pj_kyc (buckets de PEP)
    for col in ('last_year_pep', 'last_3y_pep', 'last_5y_pep', 'last_5plus_pep'):
        op.add_column('wh_pj_kyc', sa.Column(col, sa.Integer(), nullable=True))

    # company_evolution -> wh_pj_evolucao (header)
    op.create_table(
        'wh_pj_evolucao',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('unidade_administrativa_id', sa.UUID(), nullable=True),
        sa.Column('raw_id', sa.UUID(), nullable=True),
        sa.Column('cnpj', sa.String(length=14), nullable=False),
        sa.Column('funcionarios_atual', sa.Integer(), nullable=True),
        sa.Column('funcionarios_max', sa.Integer(), nullable=True),
        sa.Column('funcionarios_min', sa.Integer(), nullable=True),
        sa.Column('funcionarios_media', sa.Integer(), nullable=True),
        sa.Column('funcionarios_distintos', sa.Integer(), nullable=True),
        sa.Column('funcionarios_media_1a', sa.Integer(), nullable=True),
        sa.Column('funcionarios_media_3a', sa.Integer(), nullable=True),
        sa.Column('funcionarios_media_5a', sa.Integer(), nullable=True),
        sa.Column('crescimento_yoy_1a', sa.String(length=32), nullable=True),
        sa.Column('crescimento_yoy_3a', sa.String(length=32), nullable=True),
        sa.Column('crescimento_yoy_5a', sa.String(length=32), nullable=True),
        sa.Column('qsa_mudou', sa.Boolean(), nullable=True),
        sa.Column('faturamento_faixa_atual', sa.String(length=48), nullable=True),
        sa.Column('socios_max', sa.Integer(), nullable=True),
        sa.Column('socios_min', sa.Integer(), nullable=True),
        sa.Column('socios_media', sa.Integer(), nullable=True),
        sa.Column('socios_distintos', sa.Integer(), nullable=True),
        sa.Column('socios_media_1a', sa.Integer(), nullable=True),
        sa.Column('socios_media_3a', sa.Integer(), nullable=True),
        sa.Column('socios_media_5a', sa.Integer(), nullable=True),
        sa.Column('atividade_max', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('atividade_min', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('atividade_media', sa.Numeric(precision=6, scale=4), nullable=True),
        *_auditable(),
        *_fks(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'cnpj', 'source_type', name='uq_wh_pj_evolucao'),
    )
    _lineage_indexes('wh_pj_evolucao')

    # company_evolution -> wh_pj_evolucao_mensal (serie)
    op.create_table(
        'wh_pj_evolucao_mensal',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('unidade_administrativa_id', sa.UUID(), nullable=True),
        sa.Column('raw_id', sa.UUID(), nullable=True),
        sa.Column('cnpj', sa.String(length=14), nullable=False),
        sa.Column('mes', sa.Date(), nullable=False),
        sa.Column('funcionarios', sa.Integer(), nullable=True),
        sa.Column('faturamento_faixa', sa.String(length=48), nullable=True),
        *_auditable(),
        *_fks(),
        sa.PrimaryKeyConstraint('id'),
    )
    _lineage_indexes('wh_pj_evolucao_mensal')
    op.create_index('ix_wh_pj_evolucao_mensal_tenant_cnpj_mes', 'wh_pj_evolucao_mensal', ['tenant_id', 'cnpj', 'mes'], unique=False)


def downgrade() -> None:
    op.drop_table('wh_pj_evolucao_mensal')
    op.drop_table('wh_pj_evolucao')
    for col in ('last_5plus_pep', 'last_5y_pep', 'last_3y_pep', 'last_year_pep'):
        op.drop_column('wh_pj_kyc', col)
    for col in (
        'cnaes', 'funcionarios_faixa_media', 'funcionarios_faixa_max',
        'funcionarios_faixa_min', 'funcionarios_faixa', 'faturamento_faixa_media',
        'faturamento_faixa_max', 'faturamento_faixa_min', 'faturamento_faixa',
    ):
        op.drop_column('wh_pj_grupo_indicador', col)
    for col in ('operada_pela_familia', 'empresa_familiar', 'qtd_empresas_possuidas', 'qtd_socios'):
        op.drop_column('wh_pj_cadastro', col)
