"""ref_bacen_instituicao + ref_bacen_agencia (Sentinela CNAB F2).

Referencia publica Bacen (STR + Informes_Agencias): traduz (banco, agencia)
do CNAB em instituicao/segmento/praca. Tabelas globais, sem tenant_id.

Revision ID: c8e1f4a7b2d9
Revises: a4f7c2e9d1b3
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision = "c8e1f4a7b2d9"
down_revision = "a4f7c2e9d1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ref_bacen_instituicao",
        sa.Column("codigo_compe", sa.String(length=3), primary_key=True),
        sa.Column("ispb", sa.String(length=8), nullable=False),
        sa.Column("nome_reduzido", sa.String(length=120), nullable=False),
        sa.Column("nome_extenso", sa.String(length=255), nullable=True),
        sa.Column("participa_compe", sa.Boolean(), nullable=False),
        sa.Column("segmento", sa.String(length=30), nullable=False),
        sa.Column("segmento_fonte", sa.String(length=20), nullable=False),
        sa.Column("inicio_operacao", sa.Date(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_by_version", sa.String(length=64), nullable=False),
    )
    op.create_index(
        "ix_ref_bacen_instituicao_ispb", "ref_bacen_instituicao", ["ispb"]
    )

    op.create_table(
        "ref_bacen_agencia",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("banco_compe", sa.String(length=3), nullable=False),
        sa.Column("cnpj_base", sa.String(length=8), nullable=False),
        sa.Column("nome_if", sa.String(length=255), nullable=False),
        sa.Column("agencia_codigo", sa.String(length=5), nullable=False),
        sa.Column("nome_agencia", sa.String(length=255), nullable=True),
        sa.Column("municipio", sa.String(length=120), nullable=True),
        sa.Column("municipio_ibge", sa.Integer(), nullable=True),
        sa.Column("uf", sa.String(length=2), nullable=True),
        sa.Column("data_inicio", sa.Date(), nullable=True),
        sa.Column("posicao", sa.Date(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_by_version", sa.String(length=64), nullable=False),
        sa.UniqueConstraint(
            "banco_compe", "agencia_codigo", name="uq_ref_bacen_agencia_banco_ag"
        ),
    )
    op.create_index(
        "ix_ref_bacen_agencia_municipio", "ref_bacen_agencia", ["municipio_ibge"]
    )


def downgrade() -> None:
    op.drop_table("ref_bacen_agencia")
    op.drop_table("ref_bacen_instituicao")
