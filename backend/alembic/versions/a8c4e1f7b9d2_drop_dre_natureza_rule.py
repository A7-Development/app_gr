"""Drop wh_bitfin_dre_natureza_rule + coluna wh_dre_mensal.natureza.

Decisao 2026-06-10 (Ricardo): a DemonstrativoDeResultado do Bitfin RECALCULA
multa/juros teoricamente (percentual contratual x dias vs vencimento
original) — nao reflete caixa. A classificacao por natureza em cima dela
induz a leitura errada ("receita de mora" que nao entrou no caixa). Morre
inteira — sem residuos — para nao conviver/confundir com o catalogo de
receitas operacionais caixa-fiel (nova wh canonica, em construcao).

`wh_bitfin_tarifa_catalogo` NAO e tocada (vocabulario controlado, fica).

Revision ID: a8c4e1f7b9d2
Revises: d4e7f2a9c1b3
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a8c4e1f7b9d2"
down_revision = "d4e7f2a9c1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── coluna natureza do silver wh_dre_mensal ─────────────────────────────
    op.drop_index(op.f("ix_wh_dre_mensal_natureza"), table_name="wh_dre_mensal")
    op.drop_column("wh_dre_mensal", "natureza")

    # ── tabela de regras (indices caem junto com a tabela) ──────────────────
    op.drop_table("wh_bitfin_dre_natureza_rule")


def downgrade() -> None:
    # Recria estrutura vazia (seed das 63 regras NAO volta — ver
    # d5e9c1a3f7b2 para o seed original, se algum dia for necessario).
    op.create_table(
        "wh_bitfin_dre_natureza_rule",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fonte", sa.String(length=50), nullable=False),
        sa.Column("categoria", sa.String(length=50), nullable=False),
        sa.Column("descricao", sa.String(length=80), nullable=False),
        sa.Column("natureza", sa.String(length=20), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_wh_bitfin_dre_natureza_rule_tenant_id"),
        "wh_bitfin_dre_natureza_rule",
        ["tenant_id"],
        unique=False,
    )
    op.add_column(
        "wh_dre_mensal",
        sa.Column("natureza", sa.String(length=20), nullable=True),
    )
    op.create_index(
        op.f("ix_wh_dre_mensal_natureza"),
        "wh_dre_mensal",
        ["natureza"],
        unique=False,
    )
