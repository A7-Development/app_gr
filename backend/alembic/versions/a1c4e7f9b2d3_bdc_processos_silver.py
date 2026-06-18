"""bdc processos judiciais — silver (processo + parte + andamento + resumo)

Revision ID: a1c4e7f9b2d3
Revises: 95b297912b91
Create Date: 2026-06-18 10:00:00.000000

Dataset BDC `processes` (PROCESSOS-PJ). Andamento ganha coluna tsvector gerada
(portugues) + indice GIN pro garimpo de bens. Hand-written.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1c4e7f9b2d3"
down_revision: str | None = "95b297912b91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_TYPE = sa.Enum(
    "ERP_BITFIN", "ADMIN_QITECH", "BUREAU_SERASA_PJ", "BUREAU_SERASA_PF",
    "BUREAU_SCR_BACEN", "BUREAU_BDC", "DOCUMENT_NFE", "COBRANCA",
    "COBRANCA_BRADESCO", "COBRANCA_ITAU", "COBRANCA_BMP", "COBRANCA_VORTX",
    "SELF_DECLARED", "PEER_DECLARED", "INTERNAL_NOTE", "DERIVED",
    name="source_type", native_enum=False, length=64,
)
_TRUST_LEVEL = sa.Enum(
    "HIGH", "MEDIUM", "LOW", name="trust_level", native_enum=False, length=16,
)


def _common() -> list:
    """id + escopo (tenant/ua/raw) + cnpj — colunas comuns a todas as tabelas."""
    return [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("unidade_administrativa_id", sa.UUID(), nullable=True),
        sa.Column("raw_id", sa.UUID(), nullable=True),
        sa.Column("cnpj", sa.String(length=14), nullable=False),
    ]


def _auditable() -> list:
    return [
        sa.Column("source_type", _SOURCE_TYPE, nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("hash_origem", sa.String(length=64), nullable=True),
        sa.Column("ingested_by_version", sa.String(length=128), nullable=False),
        sa.Column("trust_level", _TRUST_LEVEL, nullable=False),
        sa.Column("collected_by", sa.UUID(), nullable=True),
    ]


def _fks() -> list:
    return [
        sa.ForeignKeyConstraint(["raw_id"], ["wh_bdc_raw_consulta.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unidade_administrativa_id"], ["cadastros_unidade_administrativa.id"], ondelete="RESTRICT"),
    ]


def _lineage(table: str, extra: tuple[str, ...] = ()) -> None:
    for col in ("cnpj", "raw_id", "source_id", "source_type", "tenant_id",
                "unidade_administrativa_id", *extra):
        op.create_index(op.f(f"ix_{table}_{col}"), table, [col], unique=False)


def upgrade() -> None:
    # ── wh_pj_processo ────────────────────────────────────────────────────
    op.create_table(
        "wh_pj_processo",
        *_common(),
        sa.Column("numero", sa.String(length=40), nullable=False),
        sa.Column("tipo", sa.String(length=160), nullable=True),
        sa.Column("assunto", sa.Text(), nullable=True),
        sa.Column("assunto_cnj", sa.String(length=160), nullable=True),
        sa.Column("assunto_cnj_amplo", sa.String(length=160), nullable=True),
        sa.Column("tribunal", sa.String(length=40), nullable=True),
        sa.Column("instancia", sa.String(length=8), nullable=True),
        sa.Column("area", sa.String(length=40), nullable=True),
        sa.Column("comarca", sa.String(length=120), nullable=True),
        sa.Column("orgao_julgador", sa.String(length=240), nullable=True),
        sa.Column("uf", sa.String(length=2), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("encerrado", sa.Boolean(), nullable=True),
        sa.Column("valor", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("polaridade_alvo", sa.String(length=12), nullable=True),
        sa.Column("is_execucao", sa.Boolean(), nullable=True),
        sa.Column("num_partes", sa.Integer(), nullable=True),
        sa.Column("num_atualizacoes", sa.Integer(), nullable=True),
        sa.Column("idade_dias", sa.Integer(), nullable=True),
        sa.Column("data_redistribuicao", sa.Date(), nullable=True),
        sa.Column("data_notice", sa.Date(), nullable=True),
        sa.Column("data_last_movement", sa.Date(), nullable=True),
        sa.Column("data_last_update", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *_auditable(),
        *_fks(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "cnpj", "numero", name="uq_wh_pj_processo"),
    )
    _lineage("wh_pj_processo", extra=("numero",))
    op.create_index("ix_wh_pj_processo_tenant_cnpj_status", "wh_pj_processo",
                    ["tenant_id", "cnpj", "status"], unique=False)

    # ── wh_pj_processo_parte ──────────────────────────────────────────────
    op.create_table(
        "wh_pj_processo_parte",
        *_common(),
        sa.Column("numero", sa.String(length=40), nullable=False),
        sa.Column("polaridade", sa.String(length=12), nullable=True),
        sa.Column("tipo_parte", sa.String(length=40), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=True),
        sa.Column("nome", sa.String(length=240), nullable=True),
        sa.Column("doc", sa.String(length=20), nullable=True),
        *_auditable(),
        *_fks(),
        sa.PrimaryKeyConstraint("id"),
    )
    _lineage("wh_pj_processo_parte")
    op.create_index("ix_wh_pj_processo_parte_tenant_cnpj_numero",
                    "wh_pj_processo_parte", ["tenant_id", "cnpj", "numero"], unique=False)
    op.create_index("ix_wh_pj_processo_parte_doc", "wh_pj_processo_parte", ["doc"], unique=False)

    # ── wh_pj_processo_andamento ──────────────────────────────────────────
    op.create_table(
        "wh_pj_processo_andamento",
        *_common(),
        sa.Column("numero", sa.String(length=40), nullable=False),
        sa.Column("data", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("conteudo_hash", sa.String(length=64), nullable=False),
        sa.Column("evento_patrimonial", sa.Boolean(), nullable=True),
        *_auditable(),
        *_fks(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "cnpj", "numero", "data", "conteudo_hash",
                            name="uq_wh_pj_processo_andamento"),
    )
    _lineage("wh_pj_processo_andamento")
    op.create_index("ix_wh_pj_processo_andamento_tenant_cnpj_numero",
                    "wh_pj_processo_andamento", ["tenant_id", "cnpj", "numero"], unique=False)
    op.create_index("ix_wh_pj_processo_andamento_patrimonial",
                    "wh_pj_processo_andamento",
                    ["tenant_id", "cnpj", "evento_patrimonial"], unique=False)
    # Full-text PT: coluna tsvector gerada + indice GIN (garimpo de bens).
    op.execute(
        "ALTER TABLE wh_pj_processo_andamento ADD COLUMN conteudo_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('portuguese', conteudo)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_wh_pj_processo_andamento_tsv ON wh_pj_processo_andamento "
        "USING gin (conteudo_tsv)"
    )

    # ── wh_pj_processo_resumo ─────────────────────────────────────────────
    op.create_table(
        "wh_pj_processo_resumo",
        *_common(),
        sa.Column("qtd_total", sa.Integer(), nullable=True),
        sa.Column("qtd_ativos", sa.Integer(), nullable=True),
        sa.Column("qtd_encerrados", sa.Integer(), nullable=True),
        sa.Column("por_area", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("qtd_como_reu", sa.Integer(), nullable=True),
        sa.Column("qtd_como_autor", sa.Integer(), nullable=True),
        sa.Column("qtd_execucoes_contra", sa.Integer(), nullable=True),
        sa.Column("credores_executando", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("qtd_recuperacao_falencia", sa.Integer(), nullable=True),
        sa.Column("valor_total_informado", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("last_30d", sa.Integer(), nullable=True),
        sa.Column("last_90d", sa.Integer(), nullable=True),
        sa.Column("last_365d", sa.Integer(), nullable=True),
        sa.Column("primeira_data", sa.Date(), nullable=True),
        sa.Column("ultima_data", sa.Date(), nullable=True),
        *_auditable(),
        *_fks(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "cnpj", "source_type", name="uq_wh_pj_processo_resumo"),
    )
    _lineage("wh_pj_processo_resumo")


def downgrade() -> None:
    op.drop_table("wh_pj_processo_resumo")
    op.drop_table("wh_pj_processo_andamento")
    op.drop_table("wh_pj_processo_parte")
    op.drop_table("wh_pj_processo")
