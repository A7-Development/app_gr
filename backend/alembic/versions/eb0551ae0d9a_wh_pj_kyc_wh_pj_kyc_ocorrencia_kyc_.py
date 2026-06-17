"""wh_pj_kyc + wh_pj_kyc_ocorrencia (kyc package)

Revision ID: eb0551ae0d9a
Revises: 6bb2625d412b
Create Date: 2026-06-16 21:46:21.129046

Cria as 2 tabelas silver do pacote KYC (BDC): header por sujeito + ocorrencias
de sancao/PEP (com match_rate e frescor por registro). Hand-written.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'eb0551ae0d9a'
down_revision: str | None = '6bb2625d412b'
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


def _auditable_cols() -> list:
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


def upgrade() -> None:
    op.create_table(
        'wh_pj_kyc',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('unidade_administrativa_id', sa.UUID(), nullable=True),
        sa.Column('raw_id', sa.UUID(), nullable=True),
        sa.Column('cnpj', sa.String(length=14), nullable=False),
        sa.Column('subject_documento', sa.String(length=14), nullable=False),
        sa.Column('subject_tipo', sa.String(length=2), nullable=True),
        sa.Column('subject_nome', sa.String(length=255), nullable=True),
        sa.Column('is_currently_pep', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_currently_sanctioned', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('was_previously_sanctioned', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('count_sanctions', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('count_peps', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('last_30_days_sanctions', sa.Integer(), nullable=True),
        sa.Column('last_90_days_sanctions', sa.Integer(), nullable=True),
        sa.Column('last_180_days_sanctions', sa.Integer(), nullable=True),
        sa.Column('last_365_days_sanctions', sa.Integer(), nullable=True),
        *_auditable_cols(),
        sa.ForeignKeyConstraint(['raw_id'], ['wh_bdc_raw_consulta.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['unidade_administrativa_id'], ['cadastros_unidade_administrativa.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'cnpj', 'subject_documento', 'source_type', name='uq_wh_pj_kyc'),
    )
    op.create_index(op.f('ix_wh_pj_kyc_cnpj'), 'wh_pj_kyc', ['cnpj'], unique=False)
    op.create_index(op.f('ix_wh_pj_kyc_raw_id'), 'wh_pj_kyc', ['raw_id'], unique=False)
    op.create_index(op.f('ix_wh_pj_kyc_source_id'), 'wh_pj_kyc', ['source_id'], unique=False)
    op.create_index(op.f('ix_wh_pj_kyc_source_type'), 'wh_pj_kyc', ['source_type'], unique=False)
    op.create_index('ix_wh_pj_kyc_tenant_cnpj', 'wh_pj_kyc', ['tenant_id', 'cnpj'], unique=False)
    op.create_index(op.f('ix_wh_pj_kyc_tenant_id'), 'wh_pj_kyc', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_wh_pj_kyc_unidade_administrativa_id'), 'wh_pj_kyc', ['unidade_administrativa_id'], unique=False)

    op.create_table(
        'wh_pj_kyc_ocorrencia',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('unidade_administrativa_id', sa.UUID(), nullable=True),
        sa.Column('raw_id', sa.UUID(), nullable=True),
        sa.Column('cnpj', sa.String(length=14), nullable=False),
        sa.Column('subject_documento', sa.String(length=14), nullable=False),
        sa.Column('subject_tipo', sa.String(length=2), nullable=True),
        sa.Column('subject_nome', sa.String(length=255), nullable=True),
        sa.Column('categoria', sa.String(length=16), nullable=False),
        sa.Column('fonte', sa.String(length=64), nullable=True),
        sa.Column('tipo', sa.String(length=128), nullable=True),
        sa.Column('match_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('name_uniqueness_score', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('nome_original', sa.String(length=255), nullable=True),
        sa.Column('nome_sancao', sa.String(length=255), nullable=True),
        sa.Column('is_current', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('data_inicio', sa.Date(), nullable=True),
        sa.Column('data_fim', sa.Date(), nullable=True),
        sa.Column('detalhe', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        *_auditable_cols(),
        sa.ForeignKeyConstraint(['raw_id'], ['wh_bdc_raw_consulta.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['unidade_administrativa_id'], ['cadastros_unidade_administrativa.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_wh_pj_kyc_ocorrencia_cnpj'), 'wh_pj_kyc_ocorrencia', ['cnpj'], unique=False)
    op.create_index(op.f('ix_wh_pj_kyc_ocorrencia_raw_id'), 'wh_pj_kyc_ocorrencia', ['raw_id'], unique=False)
    op.create_index(op.f('ix_wh_pj_kyc_ocorrencia_source_id'), 'wh_pj_kyc_ocorrencia', ['source_id'], unique=False)
    op.create_index(op.f('ix_wh_pj_kyc_ocorrencia_source_type'), 'wh_pj_kyc_ocorrencia', ['source_type'], unique=False)
    op.create_index('ix_wh_pj_kyc_ocorrencia_tenant_cnpj', 'wh_pj_kyc_ocorrencia', ['tenant_id', 'cnpj'], unique=False)
    op.create_index(op.f('ix_wh_pj_kyc_ocorrencia_tenant_id'), 'wh_pj_kyc_ocorrencia', ['tenant_id'], unique=False)
    op.create_index('ix_wh_pj_kyc_ocorrencia_tenant_subject', 'wh_pj_kyc_ocorrencia', ['tenant_id', 'subject_documento'], unique=False)
    op.create_index(op.f('ix_wh_pj_kyc_ocorrencia_unidade_administrativa_id'), 'wh_pj_kyc_ocorrencia', ['unidade_administrativa_id'], unique=False)


def downgrade() -> None:
    op.drop_table('wh_pj_kyc_ocorrencia')
    op.drop_table('wh_pj_kyc')
