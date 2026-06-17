"""wh_pj_vinculo + wh_pj_grupo_indicador (quadro societario)

Revision ID: 6bb2625d412b
Revises: 4d58236581fa
Create Date: 2026-06-16 20:12:30.808604

Cria as 2 tabelas silver do pacote Quadro Societario (BDC). O autogenerate
detectou drift pre-existente de varias outras tabelas (indices source_id/
source_type do Auditable, mudancas em saldo_tesouraria etc.) — TUDO removido
a mao; esta migration cria SOMENTE as 2 tabelas novas.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6bb2625d412b'
down_revision: str | None = '4d58236581fa'
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


def upgrade() -> None:
    op.create_table(
        'wh_pj_grupo_indicador',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('unidade_administrativa_id', sa.UUID(), nullable=True),
        sa.Column('raw_id', sa.UUID(), nullable=True),
        sa.Column('cnpj', sa.String(length=14), nullable=False),
        sa.Column('total_companies', sa.Integer(), nullable=True),
        sa.Column('total_active', sa.Integer(), nullable=True),
        sa.Column('total_inactive', sa.Integer(), nullable=True),
        sa.Column('total_people', sa.Integer(), nullable=True),
        sa.Column('total_owners', sa.Integer(), nullable=True),
        sa.Column('total_sanctioned', sa.Integer(), nullable=True),
        sa.Column('total_peps', sa.Integer(), nullable=True),
        sa.Column('total_lawsuits', sa.Integer(), nullable=True),
        sa.Column('total_bad_passages', sa.Integer(), nullable=True),
        sa.Column('avg_activity_level', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('min_company_age', sa.Integer(), nullable=True),
        sa.Column('max_company_age', sa.Integer(), nullable=True),
        sa.Column('avg_company_age', sa.Integer(), nullable=True),
        sa.Column('first_passage_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_passage_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_12m_passages', sa.Integer(), nullable=True),
        sa.Column('source_type', _SOURCE_TYPE, nullable=False),
        sa.Column('source_id', sa.String(length=255), nullable=False),
        sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('hash_origem', sa.String(length=64), nullable=True),
        sa.Column('ingested_by_version', sa.String(length=128), nullable=False),
        sa.Column('trust_level', _TRUST_LEVEL, nullable=False),
        sa.Column('collected_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['raw_id'], ['wh_bdc_raw_consulta.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['unidade_administrativa_id'], ['cadastros_unidade_administrativa.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'cnpj', 'source_type', name='uq_wh_pj_grupo_indicador'),
    )
    op.create_index(op.f('ix_wh_pj_grupo_indicador_cnpj'), 'wh_pj_grupo_indicador', ['cnpj'], unique=False)
    op.create_index(op.f('ix_wh_pj_grupo_indicador_raw_id'), 'wh_pj_grupo_indicador', ['raw_id'], unique=False)
    op.create_index(op.f('ix_wh_pj_grupo_indicador_source_id'), 'wh_pj_grupo_indicador', ['source_id'], unique=False)
    op.create_index(op.f('ix_wh_pj_grupo_indicador_source_type'), 'wh_pj_grupo_indicador', ['source_type'], unique=False)
    op.create_index(op.f('ix_wh_pj_grupo_indicador_tenant_id'), 'wh_pj_grupo_indicador', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_wh_pj_grupo_indicador_unidade_administrativa_id'), 'wh_pj_grupo_indicador', ['unidade_administrativa_id'], unique=False)

    op.create_table(
        'wh_pj_vinculo',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('unidade_administrativa_id', sa.UUID(), nullable=True),
        sa.Column('raw_id', sa.UUID(), nullable=True),
        sa.Column('cnpj', sa.String(length=14), nullable=False),
        sa.Column('documento_relacionado', sa.String(length=14), nullable=True),
        sa.Column('tipo_pessoa', sa.String(length=2), nullable=True),
        sa.Column('nome', sa.String(length=255), nullable=True),
        sa.Column('relationship_type', sa.String(length=40), nullable=True),
        sa.Column('relationship_name', sa.String(length=80), nullable=True),
        sa.Column('percentual', sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column('ativo', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('data_inicio', sa.Date(), nullable=True),
        sa.Column('data_fim', sa.Date(), nullable=True),
        sa.Column('source_type', _SOURCE_TYPE, nullable=False),
        sa.Column('source_id', sa.String(length=255), nullable=False),
        sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('hash_origem', sa.String(length=64), nullable=True),
        sa.Column('ingested_by_version', sa.String(length=128), nullable=False),
        sa.Column('trust_level', _TRUST_LEVEL, nullable=False),
        sa.Column('collected_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['raw_id'], ['wh_bdc_raw_consulta.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['unidade_administrativa_id'], ['cadastros_unidade_administrativa.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_wh_pj_vinculo_cnpj'), 'wh_pj_vinculo', ['cnpj'], unique=False)
    op.create_index(op.f('ix_wh_pj_vinculo_raw_id'), 'wh_pj_vinculo', ['raw_id'], unique=False)
    op.create_index(op.f('ix_wh_pj_vinculo_source_id'), 'wh_pj_vinculo', ['source_id'], unique=False)
    op.create_index(op.f('ix_wh_pj_vinculo_source_type'), 'wh_pj_vinculo', ['source_type'], unique=False)
    op.create_index('ix_wh_pj_vinculo_tenant_cnpj', 'wh_pj_vinculo', ['tenant_id', 'cnpj'], unique=False)
    op.create_index(op.f('ix_wh_pj_vinculo_tenant_id'), 'wh_pj_vinculo', ['tenant_id'], unique=False)
    op.create_index('ix_wh_pj_vinculo_tenant_relacionado', 'wh_pj_vinculo', ['tenant_id', 'documento_relacionado'], unique=False)
    op.create_index(op.f('ix_wh_pj_vinculo_unidade_administrativa_id'), 'wh_pj_vinculo', ['unidade_administrativa_id'], unique=False)


def downgrade() -> None:
    op.drop_table('wh_pj_vinculo')
    op.drop_table('wh_pj_grupo_indicador')
