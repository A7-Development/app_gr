"""risco_cedente_snapshot

Revision ID: d7e2a9c5f1b4
Revises: c4d8f2a6e1b7
Create Date: 2026-07-08

Espinha do Painel de Risco de Cedentes (decisao Ricardo 2026-07-08: cada
modelo do catalogo = UM INDICADOR; painel compoe N indicadores num Risco do
Cedente unico e multivariavel):

1. `cedente_risco_snapshot` — serie temporal por (cedente × indicador ×
   data_ref); modelo_id NULL = linha do risco COMPOSTO (UNIQUE NULLS NOT
   DISTINCT). Tendencia/early-warning exigem historico.
2. `cedente_risco_composicao` — pesos versionados da combinacao (append-only,
   padrao premise_set; ativa = maior version). Sem seed: a v1 e criada pelo
   service na 1a consolidacao ({"liquidacao_boleto": 1.0}).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d7e2a9c5f1b4"
down_revision: str | Sequence[str] | None = "c4d8f2a6e1b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cedente_risco_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cedente_documento", sa.String(14), nullable=False),
        sa.Column("cedente_nome", sa.String(255), nullable=True),
        sa.Column(
            "modelo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deteccao_modelo.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("data_ref", sa.Date(), nullable=False),
        sa.Column("subscore", sa.Numeric(5, 2), nullable=False),
        sa.Column("valor_avaliado", sa.Numeric(18, 2), nullable=True),
        sa.Column("valor_em_risco", sa.Numeric(18, 2), nullable=True),
        sa.Column("n_eventos", sa.Integer(), nullable=True),
        sa.Column("n_criticos", sa.Integer(), nullable=True),
        sa.Column("n_alto_risco", sa.Integer(), nullable=True),
        sa.Column("componentes", postgresql.JSONB(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # UNIQUE NULLS NOT DISTINCT: garante 1 linha composto (modelo_id NULL)
    # por cedente/dia (precedente f9b08c7d4a52).
    op.execute(
        "ALTER TABLE cedente_risco_snapshot ADD CONSTRAINT uq_cedente_risco_snapshot "
        "UNIQUE NULLS NOT DISTINCT (tenant_id, cedente_documento, modelo_id, data_ref)"
    )
    op.create_index(
        "ix_cedente_risco_snapshot_tenant_id", "cedente_risco_snapshot", ["tenant_id"]
    )
    op.create_index(
        "ix_cedente_risco_snapshot_cedente",
        "cedente_risco_snapshot",
        ["tenant_id", "cedente_documento", "data_ref"],
    )
    op.create_index(
        "ix_cedente_risco_snapshot_data_ref", "cedente_risco_snapshot", ["data_ref"]
    )

    op.create_table(
        "cedente_risco_composicao",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("pesos", postgresql.JSONB(), nullable=False),
        sa.Column("justificativa", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.UniqueConstraint("tenant_id", "version", name="uq_cedente_risco_composicao"),
    )
    op.create_index(
        "ix_cedente_risco_composicao_tenant_id",
        "cedente_risco_composicao",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_table("cedente_risco_composicao")
    op.drop_table("cedente_risco_snapshot")
