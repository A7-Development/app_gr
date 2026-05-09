"""provedores_dados baseline: 5 tabelas + seed BigDataCorp.

Revision ID: e8c4f7a2b1d3
Revises: d5bf3669b8a0
Create Date: 2026-05-05 15:30:00.000000

Fase 1 do plano "Servicos Externos > Provedores de Dados":
    - CREATE provedor_dados                                (entidade global)
    - CREATE provedor_dados_credencial                     (envelope-cifrada, sem tenant_id)
    - CREATE provedor_dados_dataset                        (catalogo dinamico)
    - CREATE provedor_dados_dataset_preco_historico        (append-only)
    - CREATE provedor_dados_sync_run                       (log de sync)
    - SEED   provedor_dados row para BigDataCorp

Sem subscription per-tenant nem usage_event nesta migration — ficam pra
Fase 3 (consumo real no modulo credito). Sem UI/router neste passo.

Decisoes de design refletidas aqui:
    - `slug` em provedor_dados e SAEnum native_enum=False (mesmo padrao de
      `ai_provider`) — armazena o `.name` da enum (ex.: 'BIGDATACORP').
    - `encrypted_payload` JSONB cifrado via envelope (`app.shared.crypto.envelope`).
      Adapter de cada vendor sabe parsear seu shape.
    - `enabled_for_sale` no dataset default false: descoberta no sync nao
      libera venda automaticamente — mantenedor revisa antes.
    - Unicidade do dataset: (provider_id, provider_dataset_code, provider_api).
      Mesmo `code` pode existir em APIs diferentes (BDC `basic_data` em
      `/people` e em `/empresas` sao datasets distintos).
    - Indice composto em preco_historico: (dataset_id, tier_index, observed_at)
      para "qual era o preco da faixa N em DD/MM" sem full scan.

Pre-requisito operacional: nenhum (tabelas novas, sem alteracao de existentes).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8c4f7a2b1d3"
down_revision: str | None = "d5bf3669b8a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# UUID deterministico do BDC — facilita seed/dev/teste sem precisar de
# lookup. NAO use isso para tenants ou dados pessoais (propositalmente
# fixo para uma row global de catalogo).
_BDC_PROVIDER_ID: str = "00000000-0000-0000-0000-0000bdc00001"


# Reuso de enums via native_enum=False — strings + CHECK (mesmo padrao
# da migration AI baseline 9a1ccaa15a01).
_data_provider_slug_enum = sa.Enum(
    "BIGDATACORP",
    "INFOSIMPLES",
    name="data_provider_slug",
    native_enum=False,
    length=32,
)

_catalog_sync_status_enum = sa.Enum(
    "OK",
    "ERROR",
    "IN_PROGRESS",
    name="catalog_sync_status",
    native_enum=False,
    length=16,
)

_price_change_kind_enum = sa.Enum(
    "INITIAL",
    "DELTA",
    "MANUAL",
    name="price_change_kind",
    native_enum=False,
    length=16,
)


def upgrade() -> None:
    # ──────────────────────────────────────────────────────────────────────
    # 1. provedor_dados
    # ──────────────────────────────────────────────────────────────────────
    op.create_table(
        "provedor_dados",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", _data_provider_slug_enum, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column(
            "default_timeout_ms",
            sa.Integer(),
            server_default="30000",
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), server_default="true", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_provedor_dados_slug"),
    )
    op.create_index(
        op.f("ix_provedor_dados_enabled"),
        "provedor_dados",
        ["enabled"],
        unique=False,
    )

    # ──────────────────────────────────────────────────────────────────────
    # 2. provedor_dados_credencial (GLOBAL — sem tenant_id)
    # ──────────────────────────────────────────────────────────────────────
    op.create_table(
        "provedor_dados_credencial",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("alias", sa.String(length=64), nullable=False),
        sa.Column(
            "encrypted_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "zdr_enabled",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "active", sa.Boolean(), server_default="true", nullable=False
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_by", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["provedor_dados.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["rotated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "alias", name="uq_provedor_dados_credencial_alias"
        ),
    )
    op.create_index(
        op.f("ix_provedor_dados_credencial_provider_id"),
        "provedor_dados_credencial",
        ["provider_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provedor_dados_credencial_active"),
        "provedor_dados_credencial",
        ["active"],
        unique=False,
    )

    # ──────────────────────────────────────────────────────────────────────
    # 3. provedor_dados_dataset
    # ──────────────────────────────────────────────────────────────────────
    op.create_table(
        "provedor_dados_dataset",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        # Camada do vendor (sync-managed)
        sa.Column(
            "provider_dataset_code", sa.String(length=128), nullable=False
        ),
        sa.Column("provider_api", sa.String(length=64), nullable=False),
        sa.Column(
            "current_cost_brl",
            sa.Numeric(precision=12, scale=6),
            nullable=True,
        ),
        sa.Column(
            "pricing_tiers_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "last_synced_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_diff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_status", sa.String(length=32), nullable=True),
        # Camada A7 (curadoria — preservada entre syncs)
        sa.Column("display_name_pt_br", sa.String(length=255), nullable=True),
        sa.Column("categoria_ui", sa.String(length=64), nullable=True),
        sa.Column("description_pt_br", sa.Text(), nullable=True),
        sa.Column(
            "enabled_for_sale",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "markup_pct", sa.Numeric(precision=6, scale=2), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["provedor_dados.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_id",
            "provider_dataset_code",
            "provider_api",
            name="uq_provedor_dados_dataset_code_api",
        ),
    )
    op.create_index(
        op.f("ix_provedor_dados_dataset_provider_id"),
        "provedor_dados_dataset",
        ["provider_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provedor_dados_dataset_provider_dataset_code"),
        "provedor_dados_dataset",
        ["provider_dataset_code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provedor_dados_dataset_provider_api"),
        "provedor_dados_dataset",
        ["provider_api"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provedor_dados_dataset_enabled_for_sale"),
        "provedor_dados_dataset",
        ["enabled_for_sale"],
        unique=False,
    )

    # ──────────────────────────────────────────────────────────────────────
    # 4. provedor_dados_sync_run
    # ──────────────────────────────────────────────────────────────────────
    # Note: criamos antes de price_history porque price_history.sync_run_id
    # tem FK pra ca.
    op.create_table(
        "provedor_dados_sync_run",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("adapter_version", sa.String(length=64), nullable=False),
        sa.Column(
            "triggered_by",
            sa.String(length=64),
            server_default="manual",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            _catalog_sync_status_enum,
            server_default="IN_PROGRESS",
            nullable=False,
        ),
        sa.Column("datasets_added", sa.Integer(), nullable=True),
        sa.Column("datasets_updated", sa.Integer(), nullable=True),
        sa.Column("datasets_unchanged", sa.Integer(), nullable=True),
        sa.Column("datasets_removed", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("credential_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["provedor_dados.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["credential_id"],
            ["provedor_dados_credencial.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_provedor_dados_sync_run_provider_id"),
        "provedor_dados_sync_run",
        ["provider_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provedor_dados_sync_run_status"),
        "provedor_dados_sync_run",
        ["status"],
        unique=False,
    )

    # ──────────────────────────────────────────────────────────────────────
    # 5. provedor_dados_dataset_preco_historico (append-only)
    # ──────────────────────────────────────────────────────────────────────
    op.create_table(
        "provedor_dados_dataset_preco_historico",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("tier_index", sa.Integer(), nullable=False),
        sa.Column("up_to_quantity", sa.Integer(), nullable=True),
        sa.Column(
            "price_brl", sa.Numeric(precision=12, scale=6), nullable=False
        ),
        sa.Column(
            "previous_price_brl",
            sa.Numeric(precision=12, scale=6),
            nullable=True,
        ),
        sa.Column("kind", _price_change_kind_enum, nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sync_run_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["provedor_dados_dataset.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sync_run_id"],
            ["provedor_dados_sync_run.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_provedor_dados_preco_dataset_tier_observed",
        "provedor_dados_dataset_preco_historico",
        ["dataset_id", "tier_index", "observed_at"],
        unique=False,
    )

    # ──────────────────────────────────────────────────────────────────────
    # SEED — BigDataCorp como provider conhecido
    # ──────────────────────────────────────────────────────────────────────
    # Nao seed credencial nem datasets — credencial entra via UI futura ou
    # script de bootstrap; datasets entram via primeiro sync de catalogo.
    op.execute(
        sa.text(
            """
            INSERT INTO provedor_dados (
                id, slug, name, base_url, default_timeout_ms,
                description, enabled
            ) VALUES (
                :id, :slug, :name, :base_url, :timeout, :description, :enabled
            )
            """
        ).bindparams(
            sa.bindparam("id", _BDC_PROVIDER_ID, type_=sa.UUID()),
            sa.bindparam("slug", "BIGDATACORP"),
            sa.bindparam("name", "BigDataCorp"),
            sa.bindparam(
                "base_url", "https://plataforma.bigdatacorp.com.br"
            ),
            sa.bindparam("timeout", 30_000),
            sa.bindparam(
                "description",
                "Provedor de dados externos (PJ/PF/processos/veiculos). "
                "Contrato A7 global; credencial unica revendida aos tenants "
                "via subscription. Endpoints sao POSTs por categoria "
                "(/empresas, /pessoas, /precos, ...) com `Datasets` no body.",
            ),
            sa.bindparam("enabled", True, type_=sa.Boolean()),
        )
    )


def downgrade() -> None:
    # Ordem reversa para respeitar FKs.
    op.drop_index(
        "ix_provedor_dados_preco_dataset_tier_observed",
        table_name="provedor_dados_dataset_preco_historico",
    )
    op.drop_table("provedor_dados_dataset_preco_historico")

    op.drop_index(
        op.f("ix_provedor_dados_sync_run_status"),
        table_name="provedor_dados_sync_run",
    )
    op.drop_index(
        op.f("ix_provedor_dados_sync_run_provider_id"),
        table_name="provedor_dados_sync_run",
    )
    op.drop_table("provedor_dados_sync_run")

    op.drop_index(
        op.f("ix_provedor_dados_dataset_enabled_for_sale"),
        table_name="provedor_dados_dataset",
    )
    op.drop_index(
        op.f("ix_provedor_dados_dataset_provider_api"),
        table_name="provedor_dados_dataset",
    )
    op.drop_index(
        op.f("ix_provedor_dados_dataset_provider_dataset_code"),
        table_name="provedor_dados_dataset",
    )
    op.drop_index(
        op.f("ix_provedor_dados_dataset_provider_id"),
        table_name="provedor_dados_dataset",
    )
    op.drop_table("provedor_dados_dataset")

    op.drop_index(
        op.f("ix_provedor_dados_credencial_active"),
        table_name="provedor_dados_credencial",
    )
    op.drop_index(
        op.f("ix_provedor_dados_credencial_provider_id"),
        table_name="provedor_dados_credencial",
    )
    op.drop_table("provedor_dados_credencial")

    op.drop_index(
        op.f("ix_provedor_dados_enabled"), table_name="provedor_dados"
    )
    op.drop_table("provedor_dados")
