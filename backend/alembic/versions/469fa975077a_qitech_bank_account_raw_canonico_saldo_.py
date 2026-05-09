"""qitech bank-account: raw + canonico (saldo + extrato)

Revision ID: 469fa975077a
Revises: e70618ebe077
Create Date: 2026-05-01 14:06:51.164529

Cria 4 tabelas para a familia QiTech `/v2/bank-account/*`:

- wh_qitech_raw_bank_account_balance     (bronze)
- wh_qitech_raw_bank_account_statement   (bronze)
- wh_saldo_bancario_diario               (silver, Auditable)
- wh_extrato_bancario                    (silver, Auditable)

Migration limpa: nao re-renomeia indices `_ua` -> `_unidade_administrativa_id`
em outras tabelas (drift detectado pelo autogenerate, mas nao escopo deste
PR). Idem para `uq_tenant_source_env_ua` e `uq_wh_qitech_raw_relatorio` --
quem precisar consolidar isso deve gerar migration dedicada.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "469fa975077a"
down_revision: str | None = "e70618ebe077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── wh_qitech_raw_bank_account_balance ──────────────────────────────────
    op.create_table(
        "wh_qitech_raw_bank_account_balance",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("unidade_administrativa_id", sa.UUID(), nullable=True),
        sa.Column("agencia", sa.String(length=20), nullable=False),
        sa.Column("conta", sa.String(length=40), nullable=False),
        sa.Column("data_posicao", sa.Date(), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_by_version", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["unidade_administrativa_id"],
            ["cadastros_unidade_administrativa.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "unidade_administrativa_id",
            "agencia",
            "conta",
            "data_posicao",
            name="uq_wh_qitech_raw_bank_account_balance",
        ),
    )
    op.create_index(
        "ix_wh_qitech_raw_bank_account_balance_conta_data",
        "wh_qitech_raw_bank_account_balance",
        ["tenant_id", "agencia", "conta", "data_posicao"],
    )
    op.create_index(
        op.f("ix_wh_qitech_raw_bank_account_balance_payload_sha256"),
        "wh_qitech_raw_bank_account_balance",
        ["payload_sha256"],
    )
    op.create_index(
        op.f("ix_wh_qitech_raw_bank_account_balance_tenant_id"),
        "wh_qitech_raw_bank_account_balance",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_wh_qitech_raw_bank_account_balance_unidade_administrativa_id"),
        "wh_qitech_raw_bank_account_balance",
        ["unidade_administrativa_id"],
    )

    # ── wh_qitech_raw_bank_account_statement ────────────────────────────────
    op.create_table(
        "wh_qitech_raw_bank_account_statement",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("unidade_administrativa_id", sa.UUID(), nullable=True),
        sa.Column("agencia", sa.String(length=20), nullable=False),
        sa.Column("conta", sa.String(length=40), nullable=False),
        sa.Column("periodo_inicio", sa.Date(), nullable=False),
        sa.Column("periodo_fim", sa.Date(), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_by_version", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["unidade_administrativa_id"],
            ["cadastros_unidade_administrativa.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "unidade_administrativa_id",
            "agencia",
            "conta",
            "periodo_inicio",
            "periodo_fim",
            name="uq_wh_qitech_raw_bank_account_statement",
        ),
    )
    op.create_index(
        "ix_wh_qitech_raw_bank_account_statement_conta_periodo",
        "wh_qitech_raw_bank_account_statement",
        ["tenant_id", "agencia", "conta", "periodo_inicio", "periodo_fim"],
    )
    op.create_index(
        op.f("ix_wh_qitech_raw_bank_account_statement_payload_sha256"),
        "wh_qitech_raw_bank_account_statement",
        ["payload_sha256"],
    )
    op.create_index(
        op.f("ix_wh_qitech_raw_bank_account_statement_tenant_id"),
        "wh_qitech_raw_bank_account_statement",
        ["tenant_id"],
    )
    op.create_index(
        op.f(
            "ix_wh_qitech_raw_bank_account_statement_unidade_administrativa_id"
        ),
        "wh_qitech_raw_bank_account_statement",
        ["unidade_administrativa_id"],
    )

    # ── wh_saldo_bancario_diario (Auditable) ────────────────────────────────
    op.create_table(
        "wh_saldo_bancario_diario",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("unidade_administrativa_id", sa.UUID(), nullable=True),
        sa.Column("data_posicao", sa.Date(), nullable=False),
        sa.Column("agencia", sa.String(length=20), nullable=False),
        sa.Column("conta", sa.String(length=40), nullable=False),
        sa.Column("banco_codigo", sa.String(length=10), nullable=True),
        sa.Column("banco_nome", sa.String(length=200), nullable=True),
        sa.Column(
            "moeda",
            sa.String(length=3),
            server_default=sa.text("'BRL'"),
            nullable=False,
        ),
        sa.Column("saldo", sa.Numeric(precision=18, scale=2), nullable=False),
        # Auditable mixin
        sa.Column(
            "source_type",
            sa.Enum(
                "ERP_BITFIN",
                "ADMIN_QITECH",
                "BUREAU_SERASA_PJ",
                "BUREAU_SERASA_PF",
                "BUREAU_SCR_BACEN",
                "DOCUMENT_NFE",
                "SELF_DECLARED",
                "PEER_DECLARED",
                "INTERNAL_NOTE",
                "DERIVED",
                name="source_type",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column(
            "source_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
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
            sa.Enum(
                "HIGH",
                "MEDIUM",
                "LOW",
                name="trust_level",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("collected_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["unidade_administrativa_id"],
            ["cadastros_unidade_administrativa.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_saldo_bancario_diario"
        ),
    )
    op.create_index(
        op.f("ix_wh_saldo_bancario_diario_agencia"),
        "wh_saldo_bancario_diario",
        ["agencia"],
    )
    op.create_index(
        op.f("ix_wh_saldo_bancario_diario_conta"),
        "wh_saldo_bancario_diario",
        ["conta"],
    )
    op.create_index(
        op.f("ix_wh_saldo_bancario_diario_data_posicao"),
        "wh_saldo_bancario_diario",
        ["data_posicao"],
    )
    op.create_index(
        op.f("ix_wh_saldo_bancario_diario_source_id"),
        "wh_saldo_bancario_diario",
        ["source_id"],
    )
    op.create_index(
        op.f("ix_wh_saldo_bancario_diario_source_type"),
        "wh_saldo_bancario_diario",
        ["source_type"],
    )
    op.create_index(
        "ix_wh_saldo_bancario_diario_tenant_conta_data",
        "wh_saldo_bancario_diario",
        ["tenant_id", "agencia", "conta", "data_posicao"],
    )
    op.create_index(
        "ix_wh_saldo_bancario_diario_tenant_data",
        "wh_saldo_bancario_diario",
        ["tenant_id", "data_posicao"],
    )
    op.create_index(
        op.f("ix_wh_saldo_bancario_diario_tenant_id"),
        "wh_saldo_bancario_diario",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_saldo_bancario_diario_tenant_ua_data",
        "wh_saldo_bancario_diario",
        ["tenant_id", "unidade_administrativa_id", "data_posicao"],
    )
    op.create_index(
        op.f("ix_wh_saldo_bancario_diario_unidade_administrativa_id"),
        "wh_saldo_bancario_diario",
        ["unidade_administrativa_id"],
    )

    # ── wh_extrato_bancario (Auditable) ─────────────────────────────────────
    op.create_table(
        "wh_extrato_bancario",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("unidade_administrativa_id", sa.UUID(), nullable=True),
        sa.Column("agencia", sa.String(length=20), nullable=False),
        sa.Column("conta", sa.String(length=40), nullable=False),
        sa.Column("banco_codigo", sa.String(length=10), nullable=True),
        sa.Column("banco_nome", sa.String(length=200), nullable=True),
        sa.Column(
            "moeda",
            sa.String(length=3),
            server_default=sa.text("'BRL'"),
            nullable=False,
        ),
        sa.Column("data_lancamento", sa.Date(), nullable=False),
        sa.Column("data_movimento", sa.Date(), nullable=True),
        sa.Column("valor", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("tipo", sa.String(length=1), nullable=False),
        sa.Column("historico", sa.String(length=255), nullable=True),
        sa.Column("descricao", sa.String(length=500), nullable=True),
        sa.Column("documento", sa.String(length=100), nullable=True),
        sa.Column("contrapartida_nome", sa.String(length=200), nullable=True),
        sa.Column("contrapartida_doc", sa.String(length=14), nullable=True),
        # Auditable mixin
        sa.Column(
            "source_type",
            sa.Enum(
                "ERP_BITFIN",
                "ADMIN_QITECH",
                "BUREAU_SERASA_PJ",
                "BUREAU_SERASA_PF",
                "BUREAU_SCR_BACEN",
                "DOCUMENT_NFE",
                "SELF_DECLARED",
                "PEER_DECLARED",
                "INTERNAL_NOTE",
                "DERIVED",
                name="source_type",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column(
            "source_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
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
            sa.Enum(
                "HIGH",
                "MEDIUM",
                "LOW",
                name="trust_level",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("collected_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["unidade_administrativa_id"],
            ["cadastros_unidade_administrativa.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_extrato_bancario"
        ),
    )
    op.create_index(
        op.f("ix_wh_extrato_bancario_data_lancamento"),
        "wh_extrato_bancario",
        ["data_lancamento"],
    )
    op.create_index(
        op.f("ix_wh_extrato_bancario_source_id"),
        "wh_extrato_bancario",
        ["source_id"],
    )
    op.create_index(
        op.f("ix_wh_extrato_bancario_source_type"),
        "wh_extrato_bancario",
        ["source_type"],
    )
    op.create_index(
        "ix_wh_extrato_bancario_tenant_conta_data",
        "wh_extrato_bancario",
        ["tenant_id", "agencia", "conta", "data_lancamento"],
    )
    op.create_index(
        "ix_wh_extrato_bancario_tenant_data",
        "wh_extrato_bancario",
        ["tenant_id", "data_lancamento"],
    )
    op.create_index(
        "ix_wh_extrato_bancario_tenant_data_valor",
        "wh_extrato_bancario",
        ["tenant_id", "data_lancamento", "valor"],
    )
    op.create_index(
        op.f("ix_wh_extrato_bancario_tenant_id"),
        "wh_extrato_bancario",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_wh_extrato_bancario_unidade_administrativa_id"),
        "wh_extrato_bancario",
        ["unidade_administrativa_id"],
    )


def downgrade() -> None:
    # Drop reverso (silver primeiro, depois bronze)
    op.drop_index(
        op.f("ix_wh_extrato_bancario_unidade_administrativa_id"),
        table_name="wh_extrato_bancario",
    )
    op.drop_index(
        op.f("ix_wh_extrato_bancario_tenant_id"),
        table_name="wh_extrato_bancario",
    )
    op.drop_index(
        "ix_wh_extrato_bancario_tenant_data_valor",
        table_name="wh_extrato_bancario",
    )
    op.drop_index(
        "ix_wh_extrato_bancario_tenant_data",
        table_name="wh_extrato_bancario",
    )
    op.drop_index(
        "ix_wh_extrato_bancario_tenant_conta_data",
        table_name="wh_extrato_bancario",
    )
    op.drop_index(
        op.f("ix_wh_extrato_bancario_source_type"),
        table_name="wh_extrato_bancario",
    )
    op.drop_index(
        op.f("ix_wh_extrato_bancario_source_id"),
        table_name="wh_extrato_bancario",
    )
    op.drop_index(
        op.f("ix_wh_extrato_bancario_data_lancamento"),
        table_name="wh_extrato_bancario",
    )
    op.drop_table("wh_extrato_bancario")

    op.drop_index(
        op.f("ix_wh_saldo_bancario_diario_unidade_administrativa_id"),
        table_name="wh_saldo_bancario_diario",
    )
    op.drop_index(
        "ix_wh_saldo_bancario_diario_tenant_ua_data",
        table_name="wh_saldo_bancario_diario",
    )
    op.drop_index(
        op.f("ix_wh_saldo_bancario_diario_tenant_id"),
        table_name="wh_saldo_bancario_diario",
    )
    op.drop_index(
        "ix_wh_saldo_bancario_diario_tenant_data",
        table_name="wh_saldo_bancario_diario",
    )
    op.drop_index(
        "ix_wh_saldo_bancario_diario_tenant_conta_data",
        table_name="wh_saldo_bancario_diario",
    )
    op.drop_index(
        op.f("ix_wh_saldo_bancario_diario_source_type"),
        table_name="wh_saldo_bancario_diario",
    )
    op.drop_index(
        op.f("ix_wh_saldo_bancario_diario_source_id"),
        table_name="wh_saldo_bancario_diario",
    )
    op.drop_index(
        op.f("ix_wh_saldo_bancario_diario_data_posicao"),
        table_name="wh_saldo_bancario_diario",
    )
    op.drop_index(
        op.f("ix_wh_saldo_bancario_diario_conta"),
        table_name="wh_saldo_bancario_diario",
    )
    op.drop_index(
        op.f("ix_wh_saldo_bancario_diario_agencia"),
        table_name="wh_saldo_bancario_diario",
    )
    op.drop_table("wh_saldo_bancario_diario")

    op.drop_index(
        op.f(
            "ix_wh_qitech_raw_bank_account_statement_unidade_administrativa_id"
        ),
        table_name="wh_qitech_raw_bank_account_statement",
    )
    op.drop_index(
        op.f("ix_wh_qitech_raw_bank_account_statement_tenant_id"),
        table_name="wh_qitech_raw_bank_account_statement",
    )
    op.drop_index(
        op.f("ix_wh_qitech_raw_bank_account_statement_payload_sha256"),
        table_name="wh_qitech_raw_bank_account_statement",
    )
    op.drop_index(
        "ix_wh_qitech_raw_bank_account_statement_conta_periodo",
        table_name="wh_qitech_raw_bank_account_statement",
    )
    op.drop_table("wh_qitech_raw_bank_account_statement")

    op.drop_index(
        op.f(
            "ix_wh_qitech_raw_bank_account_balance_unidade_administrativa_id"
        ),
        table_name="wh_qitech_raw_bank_account_balance",
    )
    op.drop_index(
        op.f("ix_wh_qitech_raw_bank_account_balance_tenant_id"),
        table_name="wh_qitech_raw_bank_account_balance",
    )
    op.drop_index(
        op.f("ix_wh_qitech_raw_bank_account_balance_payload_sha256"),
        table_name="wh_qitech_raw_bank_account_balance",
    )
    op.drop_index(
        "ix_wh_qitech_raw_bank_account_balance_conta_data",
        table_name="wh_qitech_raw_bank_account_balance",
    )
    op.drop_table("wh_qitech_raw_bank_account_balance")
