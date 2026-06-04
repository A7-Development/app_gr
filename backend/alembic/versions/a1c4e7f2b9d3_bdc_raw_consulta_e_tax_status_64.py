"""wh_bdc_raw_consulta (bronze BDC) + alarga credit_dossier_company.tax_status

A2 incr.4b — enriquecimento cadastral PJ. Cria a camada bronze das consultas
on-demand ao BigDataCorp (payload cru imutavel, §13.2) e alarga
credit_dossier_company.tax_status de 32 -> 64 chars: o BDC devolve valores como
"ATIVA - EMPRESA DOMICILIADA NO EXTERIOR" (39 chars) que estouravam String(32).

Revision ID: a1c4e7f2b9d3
Revises: e8b3f1a9c2d7
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1c4e7f2b9d3"
down_revision: str | None = "e8b3f1a9c2d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Bronze BDC ────────────────────────────────────────────────────────
    op.create_table(
        "wh_bdc_raw_consulta",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("cnpj", sa.String(length=14), nullable=False),
        sa.Column("public_code", sa.String(length=64), nullable=False),
        sa.Column("provider_api", sa.String(length=64), nullable=False),
        sa.Column("datasets", sa.String(length=255), nullable=False),
        sa.Column("query_id", sa.String(length=64), nullable=True),
        sa.Column("found", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=False),
        sa.Column("dataset_status_code", sa.SmallInteger(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("latency_ms", sa.Numeric(precision=10, scale=1), nullable=True),
        sa.Column("triggered_by", sa.String(length=255), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("fetched_by_version", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wh_bdc_raw_consulta_tenant_id",
        "wh_bdc_raw_consulta",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_bdc_raw_consulta_cnpj",
        "wh_bdc_raw_consulta",
        ["cnpj"],
    )
    op.create_index(
        "ix_wh_bdc_raw_consulta_payload_sha256",
        "wh_bdc_raw_consulta",
        ["payload_sha256"],
    )
    op.create_index(
        "ix_wh_bdc_raw_consulta_tenant_cnpj_fetched",
        "wh_bdc_raw_consulta",
        ["tenant_id", "cnpj", sa.text("fetched_at DESC")],
    )

    # ── tax_status 32 -> 64 (valores BDC com sufixo "EXTERIOR") ──────────
    op.alter_column(
        "credit_dossier_company",
        "tax_status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=True,
    )

    # ── provider_query_name (nome tecnico de QUERY, curado) ───────────────
    # Difere do provider_dataset_code (codigo de billing do /precos). A query
    # POST /empresas usa o nome tecnico minusculo (ex.: "basic_data").
    op.add_column(
        "provedor_dados_dataset",
        sa.Column("provider_query_name", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provedor_dados_dataset", "provider_query_name")
    op.alter_column(
        "credit_dossier_company",
        "tax_status",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=True,
    )
    op.drop_index(
        "ix_wh_bdc_raw_consulta_tenant_cnpj_fetched",
        table_name="wh_bdc_raw_consulta",
    )
    op.drop_index(
        "ix_wh_bdc_raw_consulta_payload_sha256",
        table_name="wh_bdc_raw_consulta",
    )
    op.drop_index(
        "ix_wh_bdc_raw_consulta_cnpj",
        table_name="wh_bdc_raw_consulta",
    )
    op.drop_index(
        "ix_wh_bdc_raw_consulta_tenant_id",
        table_name="wh_bdc_raw_consulta",
    )
    op.drop_table("wh_bdc_raw_consulta")
