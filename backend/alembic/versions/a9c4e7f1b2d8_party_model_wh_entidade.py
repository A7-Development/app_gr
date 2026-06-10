"""party model: wh_entidade + crosswalk + papel + grupo economico (F0)

Fundacao da identidade canonica (modelo entity-centric, CLAUDE.md header):

1. `wh_entidade` — 1 linha por (tenant, documento normalizado 11/14 dig.).
   Hierarquia PJ derivada do documento: documento_raiz (8 dig.) identifica a
   pessoa juridica; filiais compartilham raiz; consolidacao por raiz e lente
   de consulta, nunca merge fisico.
2. `wh_entidade_fonte` — crosswalk (source_type, id na fonte) -> entidade.
   Linhas com entidade_id NULL = quarentena (documento invalido), visivel.
3. `wh_entidade_papel` — cedente/sacado/avalista/socio/fornecedor como FATO.
   source_id = id do papel na fonte (Bitfin ClienteId/SacadoId) — ponte para
   wh_operacao.cedente_id / wh_titulo.sacado_id sem alterar essas tabelas.
4. `wh_grupo_economico` + `wh_grupo_economico_membro` — grafo curado na fonte.
5. Seed TSEC do endpoint `bitfin.entidades` (interval 360 min) espelhando
   cada linha `bitfin.full_sync` existente.

Esta revisao tambem FAZ MERGE dos dois heads divergentes
(d4e7f2a9c1b3 central-de-dados + f5c1a8b2d4e7 merge cobranca/contratos).

Nota DDL: source_type/trust_level/tipo_pessoa/papel sao StrEnum
native_enum=False sem CHECK (create_constraint default False) -> VARCHAR puro.

Revision ID: a9c4e7f1b2d8
Revises: d4e7f2a9c1b3, f5c1a8b2d4e7
Create Date: 2026-06-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9c4e7f1b2d8"
down_revision: str | Sequence[str] | None = ("d4e7f2a9c1b3", "f5c1a8b2d4e7")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _auditable_columns() -> list[sa.Column]:
    return [
        sa.Column("source_type", sa.String(length=64), nullable=False),
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
        sa.Column("trust_level", sa.String(length=16), nullable=False),
        sa.Column("collected_by", sa.UUID(), nullable=True),
    ]


def upgrade() -> None:
    # --- 1. wh_entidade ---
    op.create_table(
        "wh_entidade",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("documento", sa.String(length=14), nullable=False),
        sa.Column("tipo_pessoa", sa.String(length=4), nullable=False),
        sa.Column("documento_raiz", sa.String(length=8), nullable=True),
        sa.Column("filial_numero", sa.String(length=4), nullable=True),
        sa.Column("is_matriz", sa.Boolean(), nullable=True),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("cnae_chave", sa.String(length=10), nullable=True),
        sa.Column("cnae_denominacao", sa.String(length=255), nullable=True),
        sa.Column("porte", sa.String(length=50), nullable=True),
        sa.Column("data_constituicao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("em_recuperacao_judicial", sa.Boolean(), nullable=True),
        sa.Column(
            "data_recuperacao_judicial", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("logradouro", sa.String(length=255), nullable=True),
        sa.Column("endereco_numero", sa.String(length=30), nullable=True),
        sa.Column("complemento", sa.String(length=255), nullable=True),
        sa.Column("bairro", sa.String(length=120), nullable=True),
        sa.Column("localidade", sa.String(length=120), nullable=True),
        sa.Column("estado", sa.String(length=2), nullable=True),
        sa.Column("cep", sa.String(length=8), nullable=True),
        sa.Column("pais", sa.String(length=60), nullable=True),
        sa.Column("endereco_verificado", sa.Boolean(), nullable=True),
        sa.Column("grupo_economico_source_id", sa.Integer(), nullable=True),
        sa.Column("data_cadastro_fonte", sa.DateTime(timezone=True), nullable=True),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "documento", name="uq_wh_entidade_documento"),
    )
    op.create_index(
        op.f("ix_wh_entidade_tenant_id"), "wh_entidade", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_wh_entidade_tenant_raiz",
        "wh_entidade",
        ["tenant_id", "documento_raiz"],
        unique=False,
    )
    op.create_index(
        "ix_wh_entidade_tenant_grupo",
        "wh_entidade",
        ["tenant_id", "grupo_economico_source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_entidade_source_type"), "wh_entidade", ["source_type"], unique=False
    )
    op.create_index(
        op.f("ix_wh_entidade_source_id"), "wh_entidade", ["source_id"], unique=False
    )

    # --- 2. wh_entidade_fonte (crosswalk; proveniencia em colunas proprias) ---
    op.create_table(
        "wh_entidade_fonte",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_entity_id", sa.String(length=64), nullable=False),
        sa.Column("entidade_id", sa.UUID(), nullable=True),
        sa.Column("documento_bruto", sa.String(length=50), nullable=True),
        sa.Column("motivo_quarentena", sa.String(length=100), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_by_version", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["entidade_id"], ["wh_entidade.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_type", "source_entity_id", name="uq_wh_entidade_fonte"
        ),
    )
    op.create_index(
        op.f("ix_wh_entidade_fonte_tenant_id"),
        "wh_entidade_fonte",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_wh_entidade_fonte_entidade",
        "wh_entidade_fonte",
        ["tenant_id", "entidade_id"],
        unique=False,
    )

    # --- 3. wh_entidade_papel ---
    op.create_table(
        "wh_entidade_papel",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("entidade_id", sa.UUID(), nullable=False),
        sa.Column("papel", sa.String(length=16), nullable=False),
        sa.Column("status_fonte", sa.String(length=50), nullable=True),
        sa.Column("data_cadastro_fonte", sa.DateTime(timezone=True), nullable=True),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["entidade_id"], ["wh_entidade.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_type", "papel", "source_id",
            name="uq_wh_entidade_papel",
        ),
    )
    op.create_index(
        op.f("ix_wh_entidade_papel_tenant_id"),
        "wh_entidade_papel",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_wh_entidade_papel_entidade",
        "wh_entidade_papel",
        ["tenant_id", "entidade_id", "papel"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_entidade_papel_source_type"),
        "wh_entidade_papel",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_entidade_papel_source_id"),
        "wh_entidade_papel",
        ["source_id"],
        unique=False,
    )

    # --- 4. wh_grupo_economico + membros ---
    op.create_table(
        "wh_grupo_economico",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("segmento", sa.String(length=120), nullable=True),
        sa.Column("quantidade_membros", sa.Integer(), nullable=True),
        sa.Column("data_cadastro_fonte", sa.DateTime(timezone=True), nullable=True),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_type", "source_id", name="uq_wh_grupo_economico"
        ),
    )
    op.create_index(
        op.f("ix_wh_grupo_economico_tenant_id"),
        "wh_grupo_economico",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_grupo_economico_source_type"),
        "wh_grupo_economico",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_grupo_economico_source_id"),
        "wh_grupo_economico",
        ["source_id"],
        unique=False,
    )

    op.create_table(
        "wh_grupo_economico_membro",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("grupo_economico_id", sa.UUID(), nullable=False),
        sa.Column("entidade_id", sa.UUID(), nullable=True),
        sa.Column("vinculo", sa.String(length=120), nullable=True),
        sa.Column("data_cadastro_fonte", sa.DateTime(timezone=True), nullable=True),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["grupo_economico_id"], ["wh_grupo_economico.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["entidade_id"], ["wh_entidade.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_type", "source_id",
            name="uq_wh_grupo_economico_membro",
        ),
    )
    op.create_index(
        op.f("ix_wh_grupo_economico_membro_tenant_id"),
        "wh_grupo_economico_membro",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_wh_grupo_membro_entidade",
        "wh_grupo_economico_membro",
        ["tenant_id", "entidade_id"],
        unique=False,
    )
    op.create_index(
        "ix_wh_grupo_membro_grupo",
        "wh_grupo_economico_membro",
        ["tenant_id", "grupo_economico_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_grupo_economico_membro_source_type"),
        "wh_grupo_economico_membro",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_grupo_economico_membro_source_id"),
        "wh_grupo_economico_membro",
        ["source_id"],
        unique=False,
    )

    # --- 5. Seed TSEC do endpoint bitfin.entidades (espelha bitfin.full_sync) ---
    op.execute(
        sa.text(
            "INSERT INTO tenant_source_endpoint_config "
            "(id, tenant_id, source_type, environment, "
            " unidade_administrativa_id, endpoint_name, enabled, "
            " schedule_kind, schedule_value, created_at, updated_at) "
            "SELECT gen_random_uuid(), tenant_id, source_type, environment, "
            "       unidade_administrativa_id, 'bitfin.entidades', true, "
            "       'interval', '360', now(), now() "
            "FROM tenant_source_endpoint_config "
            "WHERE endpoint_name = 'bitfin.full_sync' "
            "ON CONFLICT ON CONSTRAINT uq_tenant_source_env_ua_endpoint "
            "DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM tenant_source_endpoint_config "
            "WHERE endpoint_name = 'bitfin.entidades'"
        )
    )
    op.drop_table("wh_grupo_economico_membro")
    op.drop_table("wh_grupo_economico")
    op.drop_table("wh_entidade_papel")
    op.drop_table("wh_entidade_fonte")
    op.drop_table("wh_entidade")
