"""warehouse_wh_bcb_agencia

Revision ID: f8c3a1e6d4b9
Revises: e5b8d2f7a3c9
Create Date: 2026-07-08

Registro historico de agencias do BCB (serie 2007-2026 via Base dos Dados,
BigQuery basedosdados.br_bcb_agencia.agencia), deduplicado ao ultimo estado
de cada agencia — INCLUI extintas (1417/Penha) com endereco+CNPJ+IBGE.
Backfill unico (scripts/backfill_bcb_agencia.py). 1o degrau da escada de
resolucao de praca; ERP sai.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f8c3a1e6d4b9"
down_revision: str | Sequence[str] | None = "e5b8d2f7a3c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wh_bcb_agencia",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("banco_compe", sa.String(3), nullable=True),
        sa.Column("agencia_codigo", sa.String(5), nullable=False),
        sa.Column("cnpj", sa.String(14), nullable=True),
        sa.Column("instituicao", sa.String(255), nullable=True),
        sa.Column("nome_agencia", sa.String(255), nullable=True),
        sa.Column("endereco", sa.String(255), nullable=True),
        sa.Column("complemento", sa.String(255), nullable=True),
        sa.Column("bairro", sa.String(255), nullable=True),
        sa.Column("cep", sa.String(9), nullable=True),
        sa.Column("municipio", sa.String(255), nullable=True),
        sa.Column("municipio_ibge", sa.Integer(), nullable=True),
        sa.Column("uf", sa.String(2), nullable=True),
        sa.Column("ddd", sa.String(3), nullable=True),
        sa.Column("fone", sa.String(20), nullable=True),
        sa.Column("segmento", sa.String(64), nullable=True),
        sa.Column("data_inicio", sa.Date(), nullable=True),
        sa.Column("primeira_competencia", sa.Integer(), nullable=True),
        sa.Column("ultima_competencia", sa.Integer(), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        # Auditable (§14.1)
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("hash_origem", sa.String(64), nullable=True),
        sa.Column("ingested_by_version", sa.String(128), nullable=False),
        sa.Column("trust_level", sa.String(16), nullable=False),
        sa.Column("collected_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "source_id", name="uq_wh_bcb_agencia"),
    )
    op.create_index("ix_wh_bcb_agencia_tenant_id", "wh_bcb_agencia", ["tenant_id"])
    op.create_index(
        "ix_wh_bcb_agencia_lookup",
        "wh_bcb_agencia",
        ["tenant_id", "banco_compe", "agencia_codigo"],
    )


def downgrade() -> None:
    op.drop_table("wh_bcb_agencia")
