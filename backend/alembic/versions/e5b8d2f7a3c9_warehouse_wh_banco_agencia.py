"""warehouse_wh_banco_agencia

Revision ID: e5b8d2f7a3c9
Revises: d7e2a9c5f1b4
Create Date: 2026-07-08

Espelho do cadastro de agencias do ERP (Bitfin BancoAgencia + Banco):
2o degrau da escada de resolucao de praca (Bacen -> cadastro ERP -> nao
resolvida). Recupera agencias extintas/renumeradas que o snapshot Olinda
perde (ex.: Bradesco 1417/Penha-RJ). Populada pelo endpoint bitfin.entidades.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5b8d2f7a3c9"
down_revision: str | Sequence[str] | None = "d7e2a9c5f1b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wh_banco_agencia",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agencia_source_id", sa.Integer(), nullable=False),
        sa.Column("banco_codigo", sa.String(3), nullable=True),
        sa.Column("banco_nome", sa.String(255), nullable=True),
        sa.Column("agencia_codigo", sa.String(10), nullable=True),
        sa.Column("agencia_digito", sa.String(2), nullable=True),
        sa.Column("localidade", sa.String(255), nullable=True),
        sa.Column("estado", sa.String(2), nullable=True),
        sa.Column("bairro", sa.String(255), nullable=True),
        sa.Column("cep", sa.String(9), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "source_id", name="uq_wh_banco_agencia"),
    )
    op.create_index("ix_wh_banco_agencia_tenant_id", "wh_banco_agencia", ["tenant_id"])
    op.create_index(
        "ix_wh_banco_agencia_lookup",
        "wh_banco_agencia",
        ["tenant_id", "banco_codigo", "agencia_codigo"],
    )


def downgrade() -> None:
    op.drop_table("wh_banco_agencia")
