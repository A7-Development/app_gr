"""concilia boletos: bronze CNAB + canonico wh_boleto + seed source_catalog

Cria a fundacao da conciliacao carteira x boletos (lado cobranca):
- wh_cnab_raw_arquivo    -- bronze: arquivo CNAB cru (remessa/retorno)
- wh_cnab_raw_ocorrencia -- bronze: registro de detalhe (raw estruturado)
- wh_boleto              -- canonico (silver) source-agnostic do boleto
- seed em source_catalog dos 3 cobradores (Bradesco, Itau, Grafeno)

Ver CLAUDE.md secao 13 (adapter/canonico) e 13.2 (bronze->silver).

Revision ID: b7e1c3a9f2d4
Revises: f9a2c7e1b4d6
Create Date: 2026-06-04

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects import postgresql

from alembic import op


def _has_table(name: str) -> bool:
    """Idempotencia: a fundacao da conciliacao pode ter sido criada via DDL
    manual antes da reconciliacao do drift de alembic (rev e8b3f1a9c2d7 da
    branch dataset_public/BDC nao estava em main). Evita 'table already
    exists' quando o alembic finalmente rodar."""
    return sa_inspect(op.get_bind()).has_table(name)

# revision identifiers, used by Alembic.
revision: str = "b7e1c3a9f2d4"
down_revision: str | None = "f9a2c7e1b4d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_TYPE_ENUM = sa.Enum(
    "ERP_BITFIN",
    "ADMIN_QITECH",
    "BUREAU_SERASA_PJ",
    "BUREAU_SERASA_PF",
    "BUREAU_SCR_BACEN",
    "DOCUMENT_NFE",
    "COBRANCA_BRADESCO",
    "COBRANCA_ITAU",
    "COBRANCA_GRAFENO",
    "SELF_DECLARED",
    "PEER_DECLARED",
    "INTERNAL_NOTE",
    "DERIVED",
    name="source_type",
    native_enum=False,
    length=64,
)
_TRUST_LEVEL_ENUM = sa.Enum(
    "HIGH", "MEDIUM", "LOW", name="trust_level", native_enum=False, length=16
)


def upgrade() -> None:
    # --- bronze: arquivo CNAB cru ---
    if _has_table("wh_cnab_raw_arquivo"):
        # Fundacao ja criada via DDL manual; nada a fazer (ver _has_table).
        return
    op.create_table(
        "wh_cnab_raw_arquivo",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("banco", sa.String(length=20), nullable=False),
        sa.Column("tipo_arquivo", sa.String(length=10), nullable=False),
        sa.Column("nome_arquivo", sa.String(length=255), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("layout", sa.String(length=40), nullable=False),
        sa.Column("data_ref", sa.Date(), nullable=True),
        sa.Column("file_source_mode", sa.String(length=20), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_by_version", sa.String(length=128), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "sha256", name="uq_wh_cnab_raw_arquivo"),
    )
    op.create_index(
        op.f("ix_wh_cnab_raw_arquivo_tenant_id"),
        "wh_cnab_raw_arquivo",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_cnab_raw_arquivo_sha256"),
        "wh_cnab_raw_arquivo",
        ["sha256"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_cnab_raw_arquivo_data_ref"),
        "wh_cnab_raw_arquivo",
        ["data_ref"],
        unique=False,
    )
    op.create_index(
        "ix_wh_cnab_raw_arquivo_tenant_banco_tipo_data",
        "wh_cnab_raw_arquivo",
        ["tenant_id", "banco", "tipo_arquivo", "data_ref"],
        unique=False,
    )

    # --- bronze: registro de detalhe (raw estruturado) ---
    op.create_table(
        "wh_cnab_raw_ocorrencia",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("arquivo_id", sa.UUID(), nullable=False),
        sa.Column("banco", sa.String(length=20), nullable=False),
        sa.Column("tipo_arquivo", sa.String(length=10), nullable=False),
        sa.Column("linha_num", sa.Integer(), nullable=False),
        sa.Column("tipo_registro", sa.String(length=20), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_by_version", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["arquivo_id"], ["wh_cnab_raw_arquivo.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wh_cnab_raw_ocorrencia_arquivo_linha",
        "wh_cnab_raw_ocorrencia",
        ["arquivo_id", "linha_num"],
        unique=False,
    )
    op.create_index(
        "ix_wh_cnab_raw_ocorrencia_tenant",
        "wh_cnab_raw_ocorrencia",
        ["tenant_id"],
        unique=False,
    )

    # --- canonico (silver): wh_boleto ---
    op.create_table(
        "wh_boleto",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("banco_origem", sa.String(length=20), nullable=False),
        sa.Column("numero_documento", sa.String(length=50), nullable=False),
        sa.Column("nosso_numero", sa.String(length=50), nullable=True),
        sa.Column("sacado_documento", sa.String(length=20), nullable=True),
        sa.Column("sacado_nome", sa.String(length=255), nullable=True),
        sa.Column("valor_boleto", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("valor_pago", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("data_vencimento", sa.Date(), nullable=False),
        sa.Column("data_pagamento", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(length=12), nullable=False),
        sa.Column("codigo_ocorrencia", sa.String(length=10), nullable=True),
        sa.Column("data_ocorrencia", sa.Date(), nullable=True),
        sa.Column("data_ref", sa.Date(), nullable=False),
        sa.Column("arquivo_id", sa.UUID(), nullable=True),
        # Auditable
        sa.Column("source_type", _SOURCE_TYPE_ENUM, nullable=False),
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
        sa.Column("trust_level", _TRUST_LEVEL_ENUM, nullable=False),
        sa.Column("collected_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["arquivo_id"], ["wh_cnab_raw_arquivo.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "banco_origem",
            "numero_documento",
            "data_ref",
            name="uq_wh_boleto",
        ),
    )
    op.create_index(
        op.f("ix_wh_boleto_tenant_id"), "wh_boleto", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_wh_boleto_data_ref"), "wh_boleto", ["data_ref"], unique=False
    )
    op.create_index(
        op.f("ix_wh_boleto_source_id"), "wh_boleto", ["source_id"], unique=False
    )
    op.create_index(
        op.f("ix_wh_boleto_source_type"), "wh_boleto", ["source_type"], unique=False
    )
    op.create_index(
        "ix_wh_boleto_tenant_data_estado_numero",
        "wh_boleto",
        ["tenant_id", "data_ref", "estado", "numero_documento"],
        unique=False,
    )

    # --- seed source_catalog (3 cobradores) ---
    op.execute(
        """
        INSERT INTO source_catalog (source_type, label, category, owner_org, description)
        VALUES
          ('COBRANCA', 'Cobranca — Inbox de retornos CNAB', 'cobranca', NULL, 'Pasta com arquivos de retorno de varios bancos cobradores; o banco e detectado por arquivo (header CNAB).'),
          ('COBRANCA_BRADESCO', 'Bradesco — Cobranca (CNAB)', 'cobranca', 'Banco Bradesco', 'Boletos de cobranca via arquivo de retorno/remessa CNAB.'),
          ('COBRANCA_ITAU', 'Itau — Cobranca (CNAB)', 'cobranca', 'Itau Unibanco', 'Boletos de cobranca via arquivo de retorno/remessa CNAB.'),
          ('COBRANCA_GRAFENO', 'Grafeno — Cobranca (CNAB)', 'cobranca', 'Grafeno', 'Boletos de cobranca via arquivo de retorno/remessa CNAB (operado via Vortx).')
        ON CONFLICT (source_type) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM source_catalog WHERE source_type IN "
        "('COBRANCA', 'COBRANCA_BRADESCO', 'COBRANCA_ITAU', 'COBRANCA_GRAFENO')"
    )
    op.drop_index("ix_wh_boleto_tenant_data_estado_numero", table_name="wh_boleto")
    op.drop_index(op.f("ix_wh_boleto_source_type"), table_name="wh_boleto")
    op.drop_index(op.f("ix_wh_boleto_source_id"), table_name="wh_boleto")
    op.drop_index(op.f("ix_wh_boleto_data_ref"), table_name="wh_boleto")
    op.drop_index(op.f("ix_wh_boleto_tenant_id"), table_name="wh_boleto")
    op.drop_table("wh_boleto")

    op.drop_index(
        "ix_wh_cnab_raw_ocorrencia_tenant", table_name="wh_cnab_raw_ocorrencia"
    )
    op.drop_index(
        "ix_wh_cnab_raw_ocorrencia_arquivo_linha",
        table_name="wh_cnab_raw_ocorrencia",
    )
    op.drop_table("wh_cnab_raw_ocorrencia")

    op.drop_index(
        "ix_wh_cnab_raw_arquivo_tenant_banco_tipo_data",
        table_name="wh_cnab_raw_arquivo",
    )
    op.drop_index(
        op.f("ix_wh_cnab_raw_arquivo_data_ref"), table_name="wh_cnab_raw_arquivo"
    )
    op.drop_index(
        op.f("ix_wh_cnab_raw_arquivo_sha256"), table_name="wh_cnab_raw_arquivo"
    )
    op.drop_index(
        op.f("ix_wh_cnab_raw_arquivo_tenant_id"), table_name="wh_cnab_raw_arquivo"
    )
    op.drop_table("wh_cnab_raw_arquivo")
