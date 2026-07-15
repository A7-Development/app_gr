"""wh_nfe_item (produtos) + colunas de transporte em wh_nfe

Revision ID: b6d2f8a1c3e9
Revises: e7a3c9f1d4b8
Create Date: 2026-07-14

Silver do documento-360: itens/produtos da nota (1:N) + transportadora/veiculo
(1:1) promovidos do raw para o silver (regra §13.2.1 -- servico le silver).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b6d2f8a1c3e9"
down_revision = "e7a3c9f1d4b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wh_nfe",
        sa.Column("transportadora_documento", sa.String(length=14), nullable=True),
    )
    op.add_column(
        "wh_nfe",
        sa.Column("transportadora_nome", sa.String(length=120), nullable=True),
    )
    op.add_column("wh_nfe", sa.Column("veiculo_placa", sa.String(length=8), nullable=True))
    op.add_column("wh_nfe", sa.Column("veiculo_uf", sa.String(length=2), nullable=True))

    op.create_table(
        "wh_nfe_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nfe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("n_item", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=60), nullable=True),
        sa.Column("descricao", sa.String(length=300), nullable=True),
        sa.Column("ncm", sa.String(length=8), nullable=True),
        sa.Column("cfop", sa.String(length=4), nullable=True),
        sa.Column("ean", sa.String(length=14), nullable=True),
        sa.Column("quantidade", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("unidade", sa.String(length=6), nullable=True),
        sa.Column("valor_unitario", sa.Numeric(precision=21, scale=10), nullable=True),
        sa.Column("valor_total", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["nfe_id"], ["wh_nfe.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nfe_id", "n_item", name="uq_wh_nfe_item_nfe_n"),
    )
    op.create_index("ix_wh_nfe_item_tenant_id", "wh_nfe_item", ["tenant_id"])
    op.create_index("ix_wh_nfe_item_nfe_id", "wh_nfe_item", ["nfe_id"])
    op.create_index(
        "ix_wh_nfe_item_tenant_nfe", "wh_nfe_item", ["tenant_id", "nfe_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_wh_nfe_item_tenant_nfe", table_name="wh_nfe_item")
    op.drop_index("ix_wh_nfe_item_nfe_id", table_name="wh_nfe_item")
    op.drop_index("ix_wh_nfe_item_tenant_id", table_name="wh_nfe_item")
    op.drop_table("wh_nfe_item")
    op.drop_column("wh_nfe", "veiculo_uf")
    op.drop_column("wh_nfe", "veiculo_placa")
    op.drop_column("wh_nfe", "transportadora_nome")
    op.drop_column("wh_nfe", "transportadora_documento")
