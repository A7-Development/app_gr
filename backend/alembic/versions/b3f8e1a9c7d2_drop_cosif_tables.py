"""drop cosif tables (engine COSIF retirado)

Remove as 3 tabelas da infraestrutura COSIF (catalogo + regras + overrides por
tenant) apos o engine COSIF ser removido do codigo em 2026-05-28. A
classificacao da renda fixa migrou para `nome_do_papel` + lastro
(`_driver_for_nome_papel`), e o balanco antigo / balancete COSIF foram
substituidos pelo balanco estrutural. Nenhum codigo de runtime referencia mais
estas tabelas.

`downgrade` recria a estrutura (vazia) — o seed historico (catalogo + regras)
nao e restaurado; recarregar via os scripts/migrations originais se necessario.

Revision ID: b3f8e1a9c7d2
Revises: e7a1c3f9b4d6
Create Date: 2026-05-28
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b3f8e1a9c7d2"
down_revision = "e7a1c3f9b4d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ordem reversa de dependencia: tabelas que referenciam cosif_catalog
    # primeiro, depois o catalogo (que e auto-referencial).
    op.drop_table("tenant_papel_classificacao")
    op.drop_table("cosif_rule")
    op.drop_table("cosif_catalog")


def downgrade() -> None:
    op.create_table(
        "cosif_catalog",
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("nome", sa.String(length=200), nullable=False),
        sa.Column("natureza", sa.String(length=1), nullable=False),
        sa.Column("parent_codigo", sa.String(length=20), nullable=True),
        sa.Column("nivel", sa.SmallInteger(), nullable=False),
        sa.Column("grupo", sa.SmallInteger(), nullable=False),
        sa.Column(
            "plano_id",
            sa.SmallInteger(),
            server_default=sa.text("5"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "natureza IN ('D','C')", name="ck_cosif_catalog_natureza"
        ),
        sa.ForeignKeyConstraint(
            ["parent_codigo"], ["cosif_catalog.codigo"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("codigo"),
    )
    op.create_index(
        "ix_cosif_catalog_parent_codigo", "cosif_catalog", ["parent_codigo"]
    )
    op.create_index("ix_cosif_catalog_grupo", "cosif_catalog", ["grupo"])

    op.create_table(
        "cosif_rule",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("silver_origin", sa.String(length=50), nullable=False),
        sa.Column("predicate_jsonb", postgresql.JSONB(), nullable=False),
        sa.Column("cosif_codigo", sa.String(length=20), nullable=True),
        sa.Column("classe_sr_mez_sub", sa.String(length=20), nullable=True),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column(
            "confidence",
            sa.String(length=10),
            server_default=sa.text("'alta'"),
            nullable=False,
        ),
        sa.Column("rule_id_humano", sa.String(length=80), nullable=False),
        sa.Column(
            "valid_from",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column(
            "classifier_version",
            sa.String(length=20),
            server_default=sa.text("'1.0.0'"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence IN ('alta','media','baixa')",
            name="ck_cosif_rule_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["cosif_codigo"], ["cosif_catalog.codigo"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rule_id_humano", name="uq_cosif_rule_rule_id_humano"
        ),
    )
    op.create_index(
        "ix_cosif_rule_busca", "cosif_rule", ["silver_origin", "priority"]
    )

    op.create_table(
        "tenant_papel_classificacao",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fundo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("silver_origin", sa.String(length=50), nullable=False),
        sa.Column("identificador", sa.String(length=80), nullable=False),
        sa.Column("cosif_override", sa.String(length=20), nullable=False),
        sa.Column("classe_sr_mez_sub", sa.String(length=20), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["cosif_override"], ["cosif_catalog.codigo"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["fundo_id"],
            ["cadastros_unidade_administrativa.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "fundo_id",
            "silver_origin",
            "identificador",
            name="uq_tenant_papel_classificacao",
        ),
    )
    op.create_index(
        "ix_tenant_papel_classificacao_lookup",
        "tenant_papel_classificacao",
        ["tenant_id", "fundo_id", "silver_origin", "identificador"],
    )
