"""warehouse: wh_caixa_snapshot + estender dim_ua com tipo + entidade ids

Revision ID: b7e2f3a8d4c9
Revises: a7c4d9e8b2f1
Create Date: 2026-05-09 14:30:00.000000

Suporte a metrica VOP Potencial (CLAUDE.md §13, §14):

1. Estende `wh_dim_unidade_administrativa` com 5 colunas estruturais:
   - `tipo` (int nullable) -- enum do Bitfin: 1=FIDC, 2=Securitizadora, NULL=Outras.
     Permite filtrar agregados de fundo sem name-matching (multi-tenant).
   - `entidade_id` (int nullable) -- entity dona da UA. Joins canonicos com
     ContaBancaria.EntidadeId, etc.
   - `entidade_id_administradora`, `entidade_id_gestora`, `entidade_id_custodiante`
     (int nullable) -- ownership estrutural.

2. Cria `wh_caixa_snapshot` -- snapshot diario de saldo de ContaBancaria de UA.
   Granularidade: 1 row por (tenant, conta_bancaria_id, data_snapshot).
   Re-rodar a sync no mesmo dia upserta a row de hoje. Historico cresce 1/dia.

   Campos especificos:
   - `data_snapshot` (date NOT NULL, indexed) -- particiona historico
   - `conta_bancaria_id`, `conta_corrente_id`, `numero`, `descricao`,
     `conta_bancaria_tipo`, `banco_id`, `agencia_id` -- identidade da conta
   - `unidade_administrativa_id` -- ownership semantico (ua_id no Bitfin)
   - `ativa`, `eh_escrow`, `eh_caucao`, `eh_travada` -- flags estruturais
   - `saldo` (Numeric 18,4 NOT NULL) -- pode ser negativo
   - Auditable mixin (proveniencia)

   Indices:
   - tenant_id (default Auditable)
   - data_snapshot
   - conta_bancaria_id
   - unidade_administrativa_id
   - composite (tenant_id, unidade_administrativa_id, data_snapshot) -- caso
     canonico do BI service (saldo de UA num intervalo).
   - source_id, source_type (default Auditable)

   UQ: (tenant_id, data_snapshot, source_id) -- idempotencia ao re-rodar sync.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7e2f3a8d4c9"
down_revision: str | None = "a7c4d9e8b2f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----- 1. ALTER wh_dim_unidade_administrativa -----
    op.add_column(
        "wh_dim_unidade_administrativa",
        sa.Column("tipo", sa.Integer(), nullable=True),
    )
    op.add_column(
        "wh_dim_unidade_administrativa",
        sa.Column("entidade_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "wh_dim_unidade_administrativa",
        sa.Column("entidade_id_administradora", sa.Integer(), nullable=True),
    )
    op.add_column(
        "wh_dim_unidade_administrativa",
        sa.Column("entidade_id_gestora", sa.Integer(), nullable=True),
    )
    op.add_column(
        "wh_dim_unidade_administrativa",
        sa.Column("entidade_id_custodiante", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_wh_dim_unidade_administrativa_tipo"),
        "wh_dim_unidade_administrativa",
        ["tipo"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_dim_unidade_administrativa_entidade_id"),
        "wh_dim_unidade_administrativa",
        ["entidade_id"],
        unique=False,
    )

    # ----- 2. CREATE TABLE wh_caixa_snapshot -----
    op.create_table(
        "wh_caixa_snapshot",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("data_snapshot", sa.Date(), nullable=False),
        sa.Column("conta_bancaria_id", sa.Integer(), nullable=False),
        sa.Column("conta_corrente_id", sa.Integer(), nullable=True),
        sa.Column("numero", sa.String(length=50), nullable=True),
        sa.Column("descricao", sa.String(length=200), nullable=True),
        sa.Column("conta_bancaria_tipo", sa.Integer(), nullable=True),
        sa.Column("banco_id", sa.Integer(), nullable=True),
        sa.Column("agencia_id", sa.Integer(), nullable=True),
        sa.Column("unidade_administrativa_id", sa.Integer(), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.Column("eh_escrow", sa.Boolean(), nullable=False),
        sa.Column("eh_caucao", sa.Boolean(), nullable=False),
        sa.Column("eh_travada", sa.Boolean(), nullable=False),
        sa.Column("saldo", sa.Numeric(precision=18, scale=4), nullable=False),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "data_snapshot",
            "source_id",
            name="uq_wh_caixa_snapshot",
        ),
    )
    op.create_index(
        op.f("ix_wh_caixa_snapshot_tenant_id"),
        "wh_caixa_snapshot",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_caixa_snapshot_data_snapshot"),
        "wh_caixa_snapshot",
        ["data_snapshot"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_caixa_snapshot_conta_bancaria_id"),
        "wh_caixa_snapshot",
        ["conta_bancaria_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_caixa_snapshot_unidade_administrativa_id"),
        "wh_caixa_snapshot",
        ["unidade_administrativa_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_caixa_snapshot_source_id"),
        "wh_caixa_snapshot",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_caixa_snapshot_source_type"),
        "wh_caixa_snapshot",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        "ix_wh_caixa_snapshot_tenant_ua_data",
        "wh_caixa_snapshot",
        ["tenant_id", "unidade_administrativa_id", "data_snapshot"],
        unique=False,
    )


def downgrade() -> None:
    # ----- Drop wh_caixa_snapshot -----
    op.drop_index("ix_wh_caixa_snapshot_tenant_ua_data", table_name="wh_caixa_snapshot")
    op.drop_index(
        op.f("ix_wh_caixa_snapshot_source_type"), table_name="wh_caixa_snapshot"
    )
    op.drop_index(
        op.f("ix_wh_caixa_snapshot_source_id"), table_name="wh_caixa_snapshot"
    )
    op.drop_index(
        op.f("ix_wh_caixa_snapshot_unidade_administrativa_id"),
        table_name="wh_caixa_snapshot",
    )
    op.drop_index(
        op.f("ix_wh_caixa_snapshot_conta_bancaria_id"),
        table_name="wh_caixa_snapshot",
    )
    op.drop_index(
        op.f("ix_wh_caixa_snapshot_data_snapshot"), table_name="wh_caixa_snapshot"
    )
    op.drop_index(
        op.f("ix_wh_caixa_snapshot_tenant_id"), table_name="wh_caixa_snapshot"
    )
    op.drop_table("wh_caixa_snapshot")

    # ----- Drop colunas estruturais de wh_dim_unidade_administrativa -----
    op.drop_index(
        op.f("ix_wh_dim_unidade_administrativa_entidade_id"),
        table_name="wh_dim_unidade_administrativa",
    )
    op.drop_index(
        op.f("ix_wh_dim_unidade_administrativa_tipo"),
        table_name="wh_dim_unidade_administrativa",
    )
    op.drop_column("wh_dim_unidade_administrativa", "entidade_id_custodiante")
    op.drop_column("wh_dim_unidade_administrativa", "entidade_id_gestora")
    op.drop_column("wh_dim_unidade_administrativa", "entidade_id_administradora")
    op.drop_column("wh_dim_unidade_administrativa", "entidade_id")
    op.drop_column("wh_dim_unidade_administrativa", "tipo")
