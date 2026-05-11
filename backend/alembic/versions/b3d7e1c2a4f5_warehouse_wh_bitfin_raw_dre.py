"""warehouse: wh_bitfin_raw_dre (bronze do DRE Bitfin)

Revision ID: b3d7e1c2a4f5
Revises: c4b9e8f2a1d3
Create Date: 2026-05-11 17:30:00.000000

Cria a camada raw (bronze) para o DRE Bitfin, conforme CLAUDE.md §13.2.

Hoje o adapter Bitfin grava direto no silver (`wh_dre_mensal`) lendo de
`ANALYTICS.dbo.vw_DRE` — sem camada raw. Isso:

- Acopla nosso silver as regras de classificacao do Bitfin (se mudarem,
  silver muda silenciosamente).
- Impede replay quando o nosso mapper mudar (regra: separar tarifa de
  saldo devedor em "Conta Grafica", etc.).
- Quebra a regra dura "toda fonte externa transacional grava em 2 camadas"
  (§13.2).

Esta migration introduz `wh_bitfin_raw_dre` com `tipo_origem` discriminador
cobrindo duas fontes:
- `demonstrativo_resultado` -- snapshot granular de `UNLTD_A7CREDIT.dbo.
  DemonstrativoDeResultado` (~5-9k linhas/competencia)
- `vw_dre` -- snapshot consolidado de `ANALYTICS.dbo.vw_DRE` (~50-100
  linhas/competencia), mantido como espelho para reconciliacao

Granularidade: 1 row de bronze = 1 fetch de competencia inteira.
`payload` e JSONB array com todas as linhas. UQ por (tenant, tipo_origem,
competencia, payload_sha256) deduplica fetch identico via
ON CONFLICT DO NOTHING; conteudo alterado gera nova row preservando
historico.

O silver `wh_dre_mensal` NAO e tocado nesta migration — refactor do
mapper para ler de bronze e PR 3 separado.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3d7e1c2a4f5'
down_revision: str | None = 'c4b9e8f2a1d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'wh_bitfin_raw_dre',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('tipo_origem', sa.String(length=50), nullable=False),
        sa.Column('competencia', sa.Date(), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('payload_sha256', sa.String(length=64), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fetched_by_version', sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'tenant_id', 'tipo_origem', 'competencia', 'payload_sha256',
            name='uq_wh_bitfin_raw_dre',
        ),
    )
    op.create_index(
        op.f('ix_wh_bitfin_raw_dre_tenant_id'),
        'wh_bitfin_raw_dre', ['tenant_id'], unique=False,
    )
    op.create_index(
        op.f('ix_wh_bitfin_raw_dre_tipo_origem'),
        'wh_bitfin_raw_dre', ['tipo_origem'], unique=False,
    )
    op.create_index(
        op.f('ix_wh_bitfin_raw_dre_competencia'),
        'wh_bitfin_raw_dre', ['competencia'], unique=False,
    )
    op.create_index(
        op.f('ix_wh_bitfin_raw_dre_payload_sha256'),
        'wh_bitfin_raw_dre', ['payload_sha256'], unique=False,
    )
    op.create_index(
        'ix_wh_bitfin_raw_dre_tenant_tipo_competencia_fetched',
        'wh_bitfin_raw_dre',
        ['tenant_id', 'tipo_origem', 'competencia', 'fetched_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_wh_bitfin_raw_dre_tenant_tipo_competencia_fetched',
        table_name='wh_bitfin_raw_dre',
    )
    op.drop_index(
        op.f('ix_wh_bitfin_raw_dre_payload_sha256'),
        table_name='wh_bitfin_raw_dre',
    )
    op.drop_index(
        op.f('ix_wh_bitfin_raw_dre_competencia'),
        table_name='wh_bitfin_raw_dre',
    )
    op.drop_index(
        op.f('ix_wh_bitfin_raw_dre_tipo_origem'),
        table_name='wh_bitfin_raw_dre',
    )
    op.drop_index(
        op.f('ix_wh_bitfin_raw_dre_tenant_id'),
        table_name='wh_bitfin_raw_dre',
    )
    op.drop_table('wh_bitfin_raw_dre')
