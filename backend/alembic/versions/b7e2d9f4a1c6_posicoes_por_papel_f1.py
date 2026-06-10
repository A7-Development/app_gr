"""party model F1: posicoes por papel (wh_posicao_cedente(_produto) + sacado)

Snapshots consolidados do Bitfin por papel, ancorados em wh_entidade.
Alimentam Carteira Ativa / Limites aprovados / Performance do EntidadePeek.

Revision ID: b7e2d9f4a1c6
Revises: a9c4e7f1b2d8
Create Date: 2026-06-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7e2d9f4a1c6"
down_revision: str | Sequence[str] | None = "a9c4e7f1b2d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("entidade_id", sa.UUID(), nullable=True),
        sa.Column("papel_source_id", sa.String(length=64), nullable=False),
    ]


def _risco_columns() -> list[sa.Column]:
    return [
        sa.Column("risco_total_qtd", sa.Integer(), nullable=True),
        sa.Column("risco_total_valor", sa.Numeric(18, 4), nullable=True),
        sa.Column("risco_vencido_qtd", sa.Integer(), nullable=True),
        sa.Column("risco_vencido_valor", sa.Numeric(18, 4), nullable=True),
        sa.Column("risco_avencer_qtd", sa.Integer(), nullable=True),
        sa.Column("risco_avencer_valor", sa.Numeric(18, 4), nullable=True),
    ]


def _liquidez_columns() -> list[sa.Column]:
    return [
        sa.Column("indice_liquidez", sa.Numeric(10, 4), nullable=True),
        sa.Column("vencimentario_liquidez", sa.Numeric(18, 4), nullable=True),
        sa.Column("liquidez_qtde_dias", sa.Integer(), nullable=True),
        sa.Column("liquidez_data_inicial", sa.DateTime(timezone=True), nullable=True),
        sa.Column("liquidez_data_final", sa.DateTime(timezone=True), nullable=True),
        sa.Column("liquidez_total_liquidados", sa.Numeric(18, 4), nullable=True),
        sa.Column("liquidez_total_recomprados", sa.Numeric(18, 4), nullable=True),
        sa.Column(
            "liquidez_total_vencidos_penalizados", sa.Numeric(18, 4), nullable=True
        ),
        sa.Column(
            "liquidez_total_vencidos_nao_penalizados", sa.Numeric(18, 4), nullable=True
        ),
        sa.Column("liquidez_data_apuracao", sa.DateTime(timezone=True), nullable=True),
    ]


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


def _common_constraints(table: str) -> list:
    return [
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entidade_id"], ["wh_entidade.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_type", "source_id", name=f"uq_{table}"
        ),
    ]


def _common_indexes(table: str) -> None:
    op.create_index(op.f(f"ix_{table}_tenant_id"), table, ["tenant_id"], unique=False)
    op.create_index(
        f"ix_{table}_entidade", table, ["tenant_id", "entidade_id"], unique=False
    )
    op.create_index(
        op.f(f"ix_{table}_papel_source_id"), table, ["papel_source_id"], unique=False
    )


def upgrade() -> None:
    op.create_table(
        "wh_posicao_cedente",
        *_base_columns(),
        sa.Column("prazo_medio_carteira", sa.Numeric(10, 4), nullable=True),
        *_risco_columns(),
        *_liquidez_columns(),
        *_auditable_columns(),
        *_common_constraints("wh_posicao_cedente"),
    )
    _common_indexes("wh_posicao_cedente")

    op.create_table(
        "wh_posicao_cedente_produto",
        *_base_columns(),
        sa.Column("produto_source_id", sa.Integer(), nullable=False),
        sa.Column("produto_sigla", sa.String(length=20), nullable=True),
        sa.Column("limite_operacional", sa.Numeric(18, 4), nullable=True),
        sa.Column("tranche", sa.Numeric(18, 4), nullable=True),
        sa.Column("indice_liquidez", sa.Numeric(10, 4), nullable=True),
        *_risco_columns(),
        sa.Column("hist_liquidacoes_qtd", sa.Integer(), nullable=True),
        sa.Column("hist_liquidacoes_valor", sa.Numeric(18, 4), nullable=True),
        sa.Column("hist_baixados_qtd", sa.Integer(), nullable=True),
        sa.Column("hist_baixados_valor", sa.Numeric(18, 4), nullable=True),
        *_auditable_columns(),
        *_common_constraints("wh_posicao_cedente_produto"),
    )
    _common_indexes("wh_posicao_cedente_produto")

    op.create_table(
        "wh_posicao_sacado",
        *_base_columns(),
        sa.Column("ticket_medio", sa.Numeric(18, 4), nullable=True),
        sa.Column("indice_pontualidade", sa.Numeric(10, 4), nullable=True),
        sa.Column("prorrogados_qtd", sa.Integer(), nullable=True),
        sa.Column("prorrogados_valor", sa.Numeric(18, 4), nullable=True),
        sa.Column("prazo_medio_prorrogacao", sa.Numeric(10, 4), nullable=True),
        sa.Column("hist_titulos_qtd", sa.Integer(), nullable=True),
        sa.Column("hist_titulos_valor", sa.Numeric(18, 4), nullable=True),
        sa.Column("hist_liquidacoes_qtd", sa.Integer(), nullable=True),
        sa.Column("hist_liquidacoes_valor", sa.Numeric(18, 4), nullable=True),
        sa.Column("hist_recompras_qtd", sa.Integer(), nullable=True),
        sa.Column("hist_recompras_valor", sa.Numeric(18, 4), nullable=True),
        *_risco_columns(),
        *_liquidez_columns(),
        *_auditable_columns(),
        *_common_constraints("wh_posicao_sacado"),
    )
    _common_indexes("wh_posicao_sacado")


def downgrade() -> None:
    op.drop_table("wh_posicao_sacado")
    op.drop_table("wh_posicao_cedente_produto")
    op.drop_table("wh_posicao_cedente")
