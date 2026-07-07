"""fiscal_nfe_cte_silver

Revision ID: f3a8c5d2e7b4
Revises: c8e1f4a7b2d9, d4c1a9f7e2b8
Create Date: 2026-07-07

Consumidor fiscal da landing zone (decisao Ricardo 2026-07-07):

1. `wh_nfe_raw_documento` / `wh_cte_raw_documento` — raw estruturado: o XML
   integral em JSONB canonico, 1 linha por documento ("consumir tudo" para
   Data Science sem modelagem previa). Sem Auditable (excecao 14.1).
2. `wh_nfe` + `wh_nfe_duplicata` — silver curado NF-e (conceitos >=95% de
   cobertura; duplicata = elo nota <-> titulo do lastro).
3. `wh_cte` + `wh_cte_nfe` — silver curado CT-e + elo com as chaves das NF-e
   transportadas (prova de transporte do lastro).

Tambem e MERGEPOINT dos heads paralelos c8e1f4a7b2d9 (Sentinela F2, ja em
prod) e d4c1a9f7e2b8 (arquiva agentes batch).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f3a8c5d2e7b4"
down_revision: str | Sequence[str] | None = ("c8e1f4a7b2d9", "d4c1a9f7e2b8")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _auditable_cols() -> list[sa.Column]:
    return [
        sa.Column("source_type", sa.String(64), nullable=False, index=True),
        sa.Column("source_id", sa.String(255), nullable=False, index=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("hash_origem", sa.String(64), nullable=True),
        sa.Column("ingested_by_version", sa.String(128), nullable=False),
        sa.Column("trust_level", sa.String(16), nullable=False),
        sa.Column("collected_by", postgresql.UUID(as_uuid=True), nullable=True),
    ]


def _raw_table(name: str, uq: str) -> None:
    op.create_table(
        name,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chave_acesso", sa.String(44), nullable=False),
        sa.Column("schema_versao", sa.String(8), nullable=True),
        sa.Column("documento", postgresql.JSONB, nullable=False),
        sa.Column(
            "file_landing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("file_landing.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("nome_arquivo_xml", sa.String(512), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("fetched_by_version", sa.String(32), nullable=False),
        sa.UniqueConstraint("tenant_id", "chave_acesso", name=uq),
    )


def upgrade() -> None:
    _raw_table("wh_nfe_raw_documento", "uq_wh_nfe_raw_tenant_chave")
    _raw_table("wh_cte_raw_documento", "uq_wh_cte_raw_tenant_chave")

    op.create_table(
        "wh_nfe",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "raw_documento_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wh_nfe_raw_documento.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("chave_acesso", sa.String(44), nullable=False),
        sa.Column("numero", sa.Integer, nullable=False),
        sa.Column("serie", sa.Integer, nullable=True),
        sa.Column("modelo", sa.String(2), nullable=True),
        sa.Column("natureza_operacao", sa.String(120), nullable=True),
        sa.Column("data_emissao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tipo_operacao", sa.String(1), nullable=True),
        sa.Column("finalidade", sa.String(1), nullable=True),
        sa.Column("emitente_documento", sa.String(14), nullable=False),
        sa.Column("emitente_nome", sa.String(120), nullable=True),
        sa.Column("emitente_uf", sa.String(2), nullable=True),
        sa.Column("emitente_municipio", sa.String(80), nullable=True),
        sa.Column("destinatario_documento", sa.String(14), nullable=True),
        sa.Column("destinatario_tipo_pessoa", sa.String(2), nullable=True),
        sa.Column("destinatario_nome", sa.String(120), nullable=True),
        sa.Column("destinatario_uf", sa.String(2), nullable=True),
        sa.Column("destinatario_municipio", sa.String(80), nullable=True),
        sa.Column("valor_produtos", sa.Numeric(15, 2), nullable=True),
        sa.Column("valor_frete", sa.Numeric(15, 2), nullable=True),
        sa.Column("valor_desconto", sa.Numeric(15, 2), nullable=True),
        sa.Column("valor_total", sa.Numeric(15, 2), nullable=True),
        sa.Column("valor_tributos", sa.Numeric(15, 2), nullable=True),
        sa.Column("modalidade_frete", sa.String(1), nullable=True),
        sa.Column("meio_pagamento", sa.String(2), nullable=True),
        sa.Column("numero_fatura", sa.String(60), nullable=True),
        sa.Column("valor_fatura_liquido", sa.Numeric(15, 2), nullable=True),
        sa.Column("cstat", sa.Integer, nullable=True),
        sa.Column("autorizada", sa.Boolean, nullable=False),
        sa.Column("protocolo", sa.String(20), nullable=True),
        sa.Column("data_autorizacao", sa.DateTime(timezone=True), nullable=True),
        *_auditable_cols(),
        sa.UniqueConstraint("tenant_id", "chave_acesso", name="uq_wh_nfe_tenant_chave"),
    )
    op.create_index("ix_wh_nfe_tenant_emitente", "wh_nfe", ["tenant_id", "emitente_documento"])
    op.create_index(
        "ix_wh_nfe_tenant_destinatario", "wh_nfe", ["tenant_id", "destinatario_documento"]
    )
    op.create_index("ix_wh_nfe_tenant_emissao", "wh_nfe", ["tenant_id", "data_emissao"])

    op.create_table(
        "wh_nfe_duplicata",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "nfe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wh_nfe.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("numero", sa.String(60), nullable=False),
        sa.Column("vencimento", sa.Date, nullable=True),
        sa.Column("valor", sa.Numeric(15, 2), nullable=True),
        sa.UniqueConstraint("nfe_id", "numero", name="uq_wh_nfe_duplicata_nfe_numero"),
    )
    op.create_index(
        "ix_wh_nfe_duplicata_tenant_venc", "wh_nfe_duplicata", ["tenant_id", "vencimento"]
    )

    op.create_table(
        "wh_cte",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "raw_documento_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wh_cte_raw_documento.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("chave_acesso", sa.String(44), nullable=False),
        sa.Column("numero", sa.Integer, nullable=False),
        sa.Column("serie", sa.Integer, nullable=True),
        sa.Column("cfop", sa.String(4), nullable=True),
        sa.Column("natureza_operacao", sa.String(120), nullable=True),
        sa.Column("data_emissao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tipo_cte", sa.String(1), nullable=True),
        sa.Column("municipio_inicio", sa.String(80), nullable=True),
        sa.Column("uf_inicio", sa.String(2), nullable=True),
        sa.Column("municipio_fim", sa.String(80), nullable=True),
        sa.Column("uf_fim", sa.String(2), nullable=True),
        sa.Column("emitente_documento", sa.String(14), nullable=False),
        sa.Column("emitente_nome", sa.String(120), nullable=True),
        sa.Column("remetente_documento", sa.String(14), nullable=True),
        sa.Column("remetente_nome", sa.String(120), nullable=True),
        sa.Column("destinatario_documento", sa.String(14), nullable=True),
        sa.Column("destinatario_nome", sa.String(120), nullable=True),
        sa.Column("expedidor_documento", sa.String(14), nullable=True),
        sa.Column("recebedor_documento", sa.String(14), nullable=True),
        sa.Column("tomador_codigo", sa.String(1), nullable=True),
        sa.Column("valor_prestacao", sa.Numeric(15, 2), nullable=True),
        sa.Column("valor_receber", sa.Numeric(15, 2), nullable=True),
        sa.Column("valor_carga", sa.Numeric(15, 2), nullable=True),
        sa.Column("produto_predominante", sa.String(120), nullable=True),
        sa.Column("cstat", sa.Integer, nullable=True),
        sa.Column("autorizada", sa.Boolean, nullable=False),
        sa.Column("protocolo", sa.String(20), nullable=True),
        sa.Column("data_autorizacao", sa.DateTime(timezone=True), nullable=True),
        *_auditable_cols(),
        sa.UniqueConstraint("tenant_id", "chave_acesso", name="uq_wh_cte_tenant_chave"),
    )
    op.create_index("ix_wh_cte_tenant_remetente", "wh_cte", ["tenant_id", "remetente_documento"])
    op.create_index("ix_wh_cte_tenant_emissao", "wh_cte", ["tenant_id", "data_emissao"])

    op.create_table(
        "wh_cte_nfe",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "cte_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wh_cte.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chave_nfe", sa.String(44), nullable=False),
        sa.UniqueConstraint("cte_id", "chave_nfe", name="uq_wh_cte_nfe_cte_chave"),
    )
    op.create_index("ix_wh_cte_nfe_tenant_chave_nfe", "wh_cte_nfe", ["tenant_id", "chave_nfe"])


def downgrade() -> None:
    op.drop_table("wh_cte_nfe")
    op.drop_table("wh_cte")
    op.drop_table("wh_nfe_duplicata")
    op.drop_table("wh_nfe")
    op.drop_table("wh_cte_raw_documento")
    op.drop_table("wh_nfe_raw_documento")
