"""warehouse_wh_conta_bancaria

Revision ID: c4d8f2a6e1b7
Revises: a1f7c3e9d5b2
Create Date: 2026-07-08

Espelho cadastral das contas bancarias por entidade (Bitfin ContaBancaria +
Banco/BancoAgencia). Consumida pela feature S1 "praca do cedente" do modelo
de deteccao de liquidacao: boleto pago na agencia onde o CEDENTE mantem
conta = sinal forte de auto-liquidacao. Populada pelo endpoint
`bitfin.entidades` (extensao do sync do party model — sem endpoint novo).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c4d8f2a6e1b7"
down_revision: str | Sequence[str] | None = "a1f7c3e9d5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wh_conta_bancaria",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entidade_source_id", sa.Integer(), nullable=False),
        sa.Column("entidade_documento", sa.String(14), nullable=True),
        sa.Column("banco_id", sa.Integer(), nullable=True),
        sa.Column("banco_codigo", sa.String(3), nullable=True),
        sa.Column("banco_nome", sa.String(255), nullable=True),
        sa.Column("banco_digital", sa.Boolean(), nullable=True),
        sa.Column("agencia_codigo", sa.String(10), nullable=True),
        sa.Column("agencia_digito", sa.String(2), nullable=True),
        sa.Column("agencia_localidade", sa.String(255), nullable=True),
        sa.Column("agencia_estado", sa.String(2), nullable=True),
        sa.Column("numero_conta", sa.String(32), nullable=True),
        sa.Column("tipo_conta", sa.String(32), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=True),
        sa.Column("escrow", sa.Boolean(), nullable=True),
        sa.Column("suporte_para_depositos", sa.Boolean(), nullable=True),
        # Auditable (CLAUDE.md §14.1)
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
        sa.UniqueConstraint("tenant_id", "source_id", name="uq_wh_conta_bancaria"),
    )
    op.create_index("ix_wh_conta_bancaria_tenant_id", "wh_conta_bancaria", ["tenant_id"])
    op.create_index(
        "ix_wh_conta_bancaria_entidade_source_id",
        "wh_conta_bancaria",
        ["entidade_source_id"],
    )
    # Lookups do S1: contas do cedente por documento; match por banco compe.
    op.create_index(
        "ix_wh_conta_bancaria_documento",
        "wh_conta_bancaria",
        ["tenant_id", "entidade_documento"],
    )
    op.create_index(
        "ix_wh_conta_bancaria_banco", "wh_conta_bancaria", ["banco_codigo"]
    )


def downgrade() -> None:
    op.drop_table("wh_conta_bancaria")
