"""wh_receita_caixa -- metodo CAIXA (3 de 3: caixa | competencia | acruo).

Desagio + tarifas do titulo apropriados na SAIDA (liquidacao/baixa/
recompra/reoperacao). Correcao de rotulagem (Ricardo 2026-06-12): o bloco
'operacao' do wh_receita_operacional (integral na efetivacao) e a
COMPETENCIA; o CAIXA reconhece quando o dinheiro volta.

Revision ID: a5d9f2c7e3b1
Revises: d8e1f3a9c5b7
Create Date: 2026-06-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a5d9f2c7e3b1"
down_revision: str | Sequence[str] | None = "d8e1f3a9c5b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wh_receita_caixa",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("evento", sa.String(length=20), nullable=False),
        sa.Column("titulo_id", sa.Integer(), nullable=False),
        sa.Column("operacao_id", sa.Integer(), nullable=True),
        sa.Column("documento", sa.String(length=40), nullable=True),
        sa.Column("valor_desagio", sa.Numeric(18, 2), nullable=False),
        sa.Column("valor_adval", sa.Numeric(18, 2), nullable=False),
        sa.Column("valor_tarifas", sa.Numeric(18, 2), nullable=False),
        sa.Column("valor_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("unidade_administrativa_id", sa.Integer(), nullable=True),
        sa.Column("cedente_entidade_id", sa.Integer(), nullable=True),
        sa.Column("cedente_nome", sa.String(length=200), nullable=True),
        sa.Column("cedente_documento", sa.String(length=20), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("hash_origem", sa.String(length=64), nullable=True),
        sa.Column("ingested_by_version", sa.String(length=128), nullable=False),
        sa.Column("trust_level", sa.String(length=16), nullable=False),
        sa.Column("collected_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_receita_caixa_source"
        ),
    )
    for name, cols in [
        (op.f("ix_wh_receita_caixa_tenant_id"), ["tenant_id"]),
        (op.f("ix_wh_receita_caixa_evento"), ["evento"]),
        (op.f("ix_wh_receita_caixa_source_type"), ["source_type"]),
        (op.f("ix_wh_receita_caixa_source_id"), ["source_id"]),
        (
            op.f("ix_wh_receita_caixa_unidade_administrativa_id"),
            ["unidade_administrativa_id"],
        ),
        ("ix_wh_receita_caixa_tenant_comp", ["tenant_id", "competencia"]),
        ("ix_wh_receita_caixa_tenant_data", ["tenant_id", "data"]),
        ("ix_wh_receita_caixa_tenant_titulo", ["tenant_id", "titulo_id"]),
    ]:
        op.create_index(name, "wh_receita_caixa", cols, unique=False)


def downgrade() -> None:
    op.drop_table("wh_receita_caixa")
