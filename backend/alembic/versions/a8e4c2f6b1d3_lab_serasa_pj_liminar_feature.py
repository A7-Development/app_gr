"""lab_serasa_pj_liminar_feature -- features p/ ciencia de dados (liminar)

Tese de laboratorio: 1 linha por consulta Serasa PJ com features
cross-sectional (negativos, mercado, payment history, cadastrais),
longitudinais (deltas vs consulta anterior do CNPJ, "zerou em bloco") e
label externo (`label_liminar` — flag Liminar do Bitfin / curadoria,
separado da inferencia `suspeita_liminar`).

Populada por app/modules/laboratorio/services/serasa_liminar_features.py
(script scripts/serasa_liminar_features_build.py). Reconstruivel do
silver; versionada por extractor_version.

Revision ID: a8e4c2f6b1d3
Revises: f6b2d8a4c1e9
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision = "a8e4c2f6b1d3"
down_revision = "f6b2d8a4c1e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lab_serasa_pj_liminar_feature",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey(
                "wh_serasa_pj_raw_relatorio.id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "consulta_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("wh_serasa_pj_consulta.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cnpj", sa.String(14), nullable=False),
        sa.Column(
            "consulted_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("origem", sa.String(16), nullable=False),
        sa.Column("msg_class", sa.String(24), nullable=False),
        sa.Column("suspeita_liminar", sa.Boolean(), nullable=False),
        sa.Column("count_pefin", sa.Integer(), nullable=False),
        sa.Column("count_refin", sa.Integer(), nullable=False),
        sa.Column("count_protesto", sa.Integer(), nullable=False),
        sa.Column("count_cheque", sa.Integer(), nullable=False),
        sa.Column("count_falencias", sa.Integer(), nullable=False),
        sa.Column("count_acoes_judiciais", sa.Integer(), nullable=False),
        sa.Column(
            "valor_total_restricoes", sa.Numeric(20, 2), nullable=True
        ),
        sa.Column("inquiries_90d", sa.Integer(), nullable=True),
        sa.Column("inquiries_12m", sa.Integer(), nullable=True),
        sa.Column("consultantes_distintos", sa.Integer(), nullable=True),
        sa.Column("tem_payment_history", sa.Boolean(), nullable=False),
        sa.Column("idade_empresa_anos", sa.Numeric(5, 1), nullable=True),
        sa.Column("rj_no_nome", sa.Boolean(), nullable=False),
        sa.Column("prev_raw_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("dias_desde_anterior", sa.Integer(), nullable=True),
        sa.Column("delta_negativos", sa.Integer(), nullable=True),
        sa.Column("categorias_zeradas", sa.Integer(), nullable=True),
        sa.Column(
            "zerou_em_bloco",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("label_liminar", sa.Boolean(), nullable=True),
        sa.Column("extractor_version", sa.String(32), nullable=False),
        sa.Column(
            "built_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "raw_id", name="uq_lab_serasa_pj_liminar_feature"
        ),
    )
    op.create_index(
        "ix_lab_serasa_pj_liminar_feature_tenant_id",
        "lab_serasa_pj_liminar_feature",
        ["tenant_id"],
    )
    op.create_index(
        "ix_lab_serasa_pj_liminar_feature_tenant_cnpj_at",
        "lab_serasa_pj_liminar_feature",
        ["tenant_id", "cnpj", "consulted_at"],
    )


def downgrade() -> None:
    op.drop_table("lab_serasa_pj_liminar_feature")
