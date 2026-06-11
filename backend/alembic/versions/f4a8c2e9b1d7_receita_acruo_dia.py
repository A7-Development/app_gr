"""wh_receita_acruo_dia -- metodo ACRUO (2 de 3: caixa | acruo | competencia).

Cota diaria da curva composta de desagio por titulo (D+1 DU, sistematica do
fundo). Derivada 100% de silver, source_type='derived'. Mora/prorrogacao/
recompra/tarifas de servico sao iguais ao caixa no metodo acruo (leitura =
uniao com wh_receita_operacional). Competencia: metodo futuro, regras a
definir pelo Ricardo.

Revision ID: f4a8c2e9b1d7
Revises: b7d2e9f4a1c6
Create Date: 2026-06-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4a8c2e9b1d7"
down_revision: str | Sequence[str] | None = "b7d2e9f4a1c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wh_receita_acruo_dia",
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
        # Auditable (CLAUDE.md 14.1) — source_type='derived'
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
            "tenant_id", "source_id", name="uq_wh_receita_acruo_dia_source"
        ),
    )
    for name, cols in [
        (op.f("ix_wh_receita_acruo_dia_tenant_id"), ["tenant_id"]),
        (op.f("ix_wh_receita_acruo_dia_evento"), ["evento"]),
        (op.f("ix_wh_receita_acruo_dia_source_type"), ["source_type"]),
        (op.f("ix_wh_receita_acruo_dia_source_id"), ["source_id"]),
        (
            op.f("ix_wh_receita_acruo_dia_unidade_administrativa_id"),
            ["unidade_administrativa_id"],
        ),
        ("ix_wh_receita_acruo_dia_tenant_comp", ["tenant_id", "competencia"]),
        ("ix_wh_receita_acruo_dia_tenant_data", ["tenant_id", "data"]),
        ("ix_wh_receita_acruo_dia_tenant_titulo", ["tenant_id", "titulo_id"]),
    ]:
        op.create_index(name, "wh_receita_acruo_dia", cols, unique=False)


def downgrade() -> None:
    op.drop_table("wh_receita_acruo_dia")
