"""warehouse: wh_bitfin_raw_debenture (bronze) + wh_posicao_debenture_dia (silver)

Serie diaria de PL de debentures por UA, denominador do ROA bruto sobre PL
debentures (analogo ao PL cotas do MEC). Bronze captura a posicao mensal
oficial (ancora) + snapshot diario do ValorAtualizado; silver consolida numa
serie diaria por (tenant, ua, dia). Ver app/warehouse/posicao_debenture.py e
bitfin_raw_debenture.py.

Revision ID: c5e9a1d7b3f0
Revises: d3b7f1a9c2e5
Create Date: 2026-06-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c5e9a1d7b3f0"
down_revision: str | None = "d3b7f1a9c2e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Bronze: wh_bitfin_raw_debenture (sem Auditable; a raw e a fonte) ──
    op.create_table(
        "wh_bitfin_raw_debenture",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("tipo_origem", sa.String(length=50), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_by_version", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "tipo_origem",
            "data_referencia",
            "payload_sha256",
            name="uq_wh_bitfin_raw_debenture",
        ),
    )
    op.create_index(
        op.f("ix_wh_bitfin_raw_debenture_tenant_id"),
        "wh_bitfin_raw_debenture",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_bitfin_raw_debenture_tipo_origem"),
        "wh_bitfin_raw_debenture",
        ["tipo_origem"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_bitfin_raw_debenture_data_referencia"),
        "wh_bitfin_raw_debenture",
        ["data_referencia"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_bitfin_raw_debenture_payload_sha256"),
        "wh_bitfin_raw_debenture",
        ["payload_sha256"],
        unique=False,
    )
    op.create_index(
        "ix_wh_bitfin_raw_debenture_tenant_tipo_data_fetched",
        "wh_bitfin_raw_debenture",
        ["tenant_id", "tipo_origem", "data_referencia", "fetched_at"],
        unique=False,
    )

    # ── Silver: wh_posicao_debenture_dia (Auditable) ──
    op.create_table(
        "wh_posicao_debenture_dia",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("unidade_administrativa_id", sa.Integer(), nullable=False),
        sa.Column("data_posicao", sa.Date(), nullable=False),
        sa.Column("pl_bruto", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column(
            "pl_valor",
            sa.Numeric(precision=18, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "pl_liquido",
            sa.Numeric(precision=18, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "quantidade_debentures",
            sa.Numeric(precision=24, scale=8),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "n_subscricoes",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("origem", sa.String(length=20), nullable=False),
        # Auditable
        sa.Column(
            "source_type",
            sa.Enum(
                "ERP_BITFIN", "ADMIN_QITECH", "BUREAU_SERASA_REFINHO",
                "BUREAU_SERASA_PFIN", "BUREAU_SCR_BACEN", "DOCUMENT_NFE",
                "SELF_DECLARED", "PEER_DECLARED", "INTERNAL_NOTE", "DERIVED",
                name="source_type", native_enum=False, length=64,
            ),
            nullable=False,
        ),
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
        sa.Column(
            "trust_level",
            sa.Enum("HIGH", "MEDIUM", "LOW", name="trust_level",
                    native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("collected_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "unidade_administrativa_id",
            "data_posicao",
            name="uq_wh_posicao_debenture_dia",
        ),
    )
    op.create_index(
        op.f("ix_wh_posicao_debenture_dia_tenant_id"),
        "wh_posicao_debenture_dia",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_posicao_debenture_dia_unidade_administrativa_id"),
        "wh_posicao_debenture_dia",
        ["unidade_administrativa_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_posicao_debenture_dia_data_posicao"),
        "wh_posicao_debenture_dia",
        ["data_posicao"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_posicao_debenture_dia_origem"),
        "wh_posicao_debenture_dia",
        ["origem"],
        unique=False,
    )
    op.create_index(
        "ix_wh_posicao_debenture_dia_tenant_ua_data",
        "wh_posicao_debenture_dia",
        ["tenant_id", "unidade_administrativa_id", "data_posicao"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wh_posicao_debenture_dia_tenant_ua_data",
        table_name="wh_posicao_debenture_dia",
    )
    op.drop_index(
        op.f("ix_wh_posicao_debenture_dia_origem"),
        table_name="wh_posicao_debenture_dia",
    )
    op.drop_index(
        op.f("ix_wh_posicao_debenture_dia_data_posicao"),
        table_name="wh_posicao_debenture_dia",
    )
    op.drop_index(
        op.f("ix_wh_posicao_debenture_dia_unidade_administrativa_id"),
        table_name="wh_posicao_debenture_dia",
    )
    op.drop_index(
        op.f("ix_wh_posicao_debenture_dia_tenant_id"),
        table_name="wh_posicao_debenture_dia",
    )
    op.drop_table("wh_posicao_debenture_dia")

    op.drop_index(
        "ix_wh_bitfin_raw_debenture_tenant_tipo_data_fetched",
        table_name="wh_bitfin_raw_debenture",
    )
    op.drop_index(
        op.f("ix_wh_bitfin_raw_debenture_payload_sha256"),
        table_name="wh_bitfin_raw_debenture",
    )
    op.drop_index(
        op.f("ix_wh_bitfin_raw_debenture_data_referencia"),
        table_name="wh_bitfin_raw_debenture",
    )
    op.drop_index(
        op.f("ix_wh_bitfin_raw_debenture_tipo_origem"),
        table_name="wh_bitfin_raw_debenture",
    )
    op.drop_index(
        op.f("ix_wh_bitfin_raw_debenture_tenant_id"),
        table_name="wh_bitfin_raw_debenture",
    )
    op.drop_table("wh_bitfin_raw_debenture")
