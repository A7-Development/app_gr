"""Infosimples protesto -- silver (wh_protesto_*) + seed de datasets.

1. Tabelas silver canonicas (Auditable):
     wh_protesto_consulta  -- header (escopo nacional | sp_detalhe) + contadores
     wh_protesto_titulo    -- 1 linha por titulo protestado (+ credor onde houver)
   Bronze e o generico `wh_infosimples_raw_consulta` (ja existe).
2. Seed (idempotente) dos 2 datasets white-label do Infosimples:
     PROTESTO-NACIONAL    -> ieptb/protestos             (todos estados, sem credor)
     PROTESTO-SP-DETALHE  -> ieptb/protestos/detalhes-sp (SP, com cedente/apresentante)
   `provider_query_name` (path no vendor) e CURADO -- divergencia com a doc se
   corrige por UPDATE, sem deploy.

Contexto: Provimento CNJ 225/2026 murou o credor na consulta publica nacional;
o detalhe SP ainda traz `nome_cedente`/`nome_apresentante` (doc Infosimples
v2.2.37). `enabled_for_sale=false` -- ativar e decisao comercial posterior.

Revision ID: c1d7f3a2b6e4
Revises: a1c4e7f9b2d3
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "c1d7f3a2b6e4"
down_revision: str | None = "a1c4e7f9b2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DATASETS = [
    {
        "public_code": "PROTESTO-NACIONAL",
        "provider_api": "CENPROT",
        "provider_dataset_code": "IEPTB_PROTESTOS",
        "provider_query_name": "ieptb/protestos",
        "display_name_pt_br": "Protestos · IEPTB/CENPROT (nacional)",
        "categoria_ui": "restritivos",
        "description_pt_br": (
            "Existencia e dados de protestos de CPF/CNPJ no IEPTB/CENPROT "
            "(todos os estados): agregados por estado/cartorio e titulos "
            "(data/valor). Por forca do Provimento CNJ 225/2026, NAO identifica "
            "o credor."
        ),
    },
    {
        "public_code": "PROTESTO-SP-DETALHE",
        "provider_api": "CENPROT",
        "provider_dataset_code": "IEPTB_PROTESTOS_DETALHES_SP",
        "provider_query_name": "ieptb/protestos/detalhes-sp",
        "display_name_pt_br": "Protestos · Detalhe por cartorio (SP)",
        "categoria_ui": "restritivos",
        "description_pt_br": (
            "Detalhe dos protestos de um cartorio de SP (via token "
            "obter_detalhes da consulta nacional): por titulo, traz "
            "nome_cedente (credor) e nome_apresentante. +R$0,06/chamada e "
            "limite diario por login GOV.BR."
        ),
    },
]


def _auditable_columns() -> list[sa.Column]:
    # native_enum=False no modelo -> colunas VARCHAR (sem PG enum / sem CHECK).
    # Sem index=True aqui: os indices de source_type/source_id sao criados
    # EXPLICITAMENTE em upgrade() (op.create_index) — index=True duplicaria o
    # nome ix_<tabela>_source_type e quebraria com DuplicateTable.
    return [
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column(
            "source_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("hash_origem", sa.String(64), nullable=True),
        sa.Column("ingested_by_version", sa.String(128), nullable=False),
        sa.Column(
            "trust_level",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'high'"),
        ),
        sa.Column("collected_by", UUID(as_uuid=True), nullable=True),
    ]


def upgrade() -> None:
    # ── wh_protesto_consulta (header) ─────────────────────────────────────
    op.create_table(
        "wh_protesto_consulta",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_id",
            UUID(as_uuid=True),
            sa.ForeignKey("wh_infosimples_raw_consulta.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("documento", sa.String(20), nullable=False),
        sa.Column("documento_tipo", sa.String(8), nullable=False),
        sa.Column("escopo", sa.String(16), nullable=False),
        sa.Column("uf_consultada", sa.String(2), nullable=True),
        sa.Column("consultado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "constam_protestos",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "qtd_total", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("valor_total", sa.Numeric(18, 2), nullable=True),
        sa.Column(
            "com_credor",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("observacoes", sa.Text(), nullable=True),
        *_auditable_columns(),
        sa.UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_protesto_consulta"
        ),
    )
    op.create_index(
        "ix_wh_protesto_consulta_tenant_id", "wh_protesto_consulta", ["tenant_id"]
    )
    op.create_index(
        "ix_wh_protesto_consulta_raw_id", "wh_protesto_consulta", ["raw_id"]
    )
    op.create_index(
        "ix_wh_protesto_consulta_documento", "wh_protesto_consulta", ["documento"]
    )
    op.create_index(
        "ix_wh_protesto_consulta_escopo", "wh_protesto_consulta", ["escopo"]
    )
    op.create_index(
        "ix_wh_protesto_consulta_source_type",
        "wh_protesto_consulta",
        ["source_type"],
    )
    op.create_index(
        "ix_wh_protesto_consulta_source_id",
        "wh_protesto_consulta",
        ["source_id"],
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_wh_protesto_consulta_tenant_doc_consultado "
            "ON wh_protesto_consulta (tenant_id, documento, consultado_em DESC)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_wh_protesto_consulta_tenant_constam "
            "ON wh_protesto_consulta (tenant_id, documento) "
            "WHERE constam_protestos = true"
        )
    )

    # ── wh_protesto_titulo (filha) ────────────────────────────────────────
    op.create_table(
        "wh_protesto_titulo",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "consulta_id",
            UUID(as_uuid=True),
            sa.ForeignKey("wh_protesto_consulta.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cartorio", sa.Text(), nullable=True),
        sa.Column("cartorio_numero", sa.String(16), nullable=True),
        sa.Column("cidade", sa.String(128), nullable=True),
        sa.Column("uf", sa.String(2), nullable=True),
        sa.Column("data_protesto", sa.Date(), nullable=True),
        sa.Column("data_vencimento", sa.Date(), nullable=True),
        sa.Column("valor", sa.Numeric(18, 2), nullable=True),
        sa.Column("credor", sa.Text(), nullable=True),
        sa.Column("documento_credor", sa.String(20), nullable=True),
        sa.Column("especie", sa.String(64), nullable=True),
        sa.Column("detalhe", JSONB(), nullable=True),
        *_auditable_columns(),
        sa.UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_protesto_titulo"
        ),
    )
    op.create_index(
        "ix_wh_protesto_titulo_tenant_id", "wh_protesto_titulo", ["tenant_id"]
    )
    op.create_index(
        "ix_wh_protesto_titulo_consulta_id",
        "wh_protesto_titulo",
        ["consulta_id"],
    )
    op.create_index(
        "ix_wh_protesto_titulo_uf", "wh_protesto_titulo", ["uf"]
    )
    op.create_index(
        "ix_wh_protesto_titulo_source_type",
        "wh_protesto_titulo",
        ["source_type"],
    )
    op.create_index(
        "ix_wh_protesto_titulo_source_id", "wh_protesto_titulo", ["source_id"]
    )
    op.create_index(
        "ix_wh_protesto_titulo_tenant_consulta",
        "wh_protesto_titulo",
        ["tenant_id", "consulta_id"],
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_wh_protesto_titulo_tenant_com_credor "
            "ON wh_protesto_titulo (tenant_id, consulta_id) "
            "WHERE credor IS NOT NULL"
        )
    )

    # ── Seed datasets (white-label, idempotente) ──────────────────────────
    bind = op.get_bind()
    for d in _DATASETS:
        bind.execute(
            sa.text(
                "INSERT INTO provedor_dados_dataset "
                "(id, provider_id, provider_dataset_code, provider_api, "
                " public_code, provider_query_name, display_name_pt_br, "
                " categoria_ui, description_pt_br, enabled_for_sale, "
                " created_at, updated_at) "
                "SELECT gen_random_uuid(), p.id, :provider_dataset_code, "
                "       :provider_api, :public_code, :provider_query_name, "
                "       :display_name_pt_br, :categoria_ui, :description_pt_br, "
                "       false, NOW(), NOW() "
                "FROM provedor_dados p WHERE p.slug = 'INFOSIMPLES' "
                "AND NOT EXISTS (SELECT 1 FROM provedor_dados_dataset "
                "                WHERE public_code = :public_code)"
            ).bindparams(**d)
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM provedor_dados_dataset WHERE public_code IN "
            "('PROTESTO-NACIONAL','PROTESTO-SP-DETALHE')"
        )
    )
    op.drop_table("wh_protesto_titulo")
    op.drop_table("wh_protesto_consulta")
