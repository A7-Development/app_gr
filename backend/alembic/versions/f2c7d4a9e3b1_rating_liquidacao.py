"""rating_liquidacao

Revision ID: f2c7d4a9e3b1
Revises: d7f2a9c4e1b8
Create Date: 2026-07-11

PR 4 do framework do rating deterministico de liquidacao:

1. `rating_liquidacao` — snapshot vigente do rating em 2 graos (par
   cedente x sacado + rollup por cedente; sacado_documento NULL = rollup).
   Score 0-100 sobre eventos de pagamento alegado; recompra/perda/baixa
   administrativa ficam na COBERTURA (integridade != credito). Memoria de
   calculo completa em `componentes` (§14.3).
2. Parametros da formula na `deteccao_parametro` (versionados): deducoes
   por severidade, teto critico, janela, cortes de grade e portao de
   confianca (grade boa exige n e cobertura minimos).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f2c7d4a9e3b1"
down_revision: str | Sequence[str] | None = "d7f2a9c4e1b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rating_liquidacao",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cedente_documento", sa.String(20), nullable=False),
        sa.Column("cedente_nome", sa.String(255), nullable=True),
        sa.Column("sacado_documento", sa.String(20), nullable=True),
        sa.Column("sacado_nome", sa.String(255), nullable=True),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("grade", sa.String(2), nullable=False),
        sa.Column("tem_critico", sa.Boolean(), nullable=False),
        sa.Column("n_eventos_score", sa.Integer(), nullable=False),
        sa.Column("n_desfechos", sa.Integer(), nullable=False),
        sa.Column("valor_desfechos", sa.Numeric(18, 2), nullable=False),
        sa.Column("cobertura", sa.Numeric(6, 4), nullable=False),
        sa.Column("componentes", postgresql.JSONB, nullable=False),
        sa.Column("formula_version", sa.String(40), nullable=False),
        sa.Column(
            "calculado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_rating_liquidacao_tenant_id", "rating_liquidacao", ["tenant_id"])
    op.create_index(
        "ix_rating_liquidacao_cedente",
        "rating_liquidacao",
        ["tenant_id", "cedente_documento"],
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_rating_liquidacao_escopo ON rating_liquidacao "
        "(tenant_id, cedente_documento, sacado_documento) NULLS NOT DISTINCT"
    )

    params = sa.table(
        "deteccao_parametro",
        sa.column("nome", sa.String),
        sa.column("valor", postgresql.JSONB),
        sa.column("version", sa.Integer),
        sa.column("motivo", sa.String),
        sa.column("criado_por", sa.String),
    )
    motivo = "seed f2c7d4a9e3b1 — formula v1 do rating (proposta aprovada 2026-07-11)"
    op.bulk_insert(
        params,
        [
            {"nome": n, "valor": v, "version": 1, "motivo": motivo, "criado_por": "migration"}
            for n, v in (
                ("rating_janela_dias", 365),
                ("rating_deducao_alta", 15),
                ("rating_deducao_media", 5),
                ("rating_teto_critico", 20),
                ("rating_n_minimo_grade_boa", 20),
                ("rating_cobertura_minima_grade_boa", 0.5),
                ("rating_grade_a", 85),
                ("rating_grade_b", 70),
                ("rating_grade_c", 50),
                ("rating_grade_d", 30),
            )
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM deteccao_parametro WHERE nome LIKE 'rating_%' AND version = 1"
    )
    op.drop_index("ix_rating_liquidacao_cedente", table_name="rating_liquidacao")
    op.drop_index("ix_rating_liquidacao_tenant_id", table_name="rating_liquidacao")
    op.drop_table("rating_liquidacao")
