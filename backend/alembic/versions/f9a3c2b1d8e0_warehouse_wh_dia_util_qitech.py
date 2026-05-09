"""warehouse: wh_dia_util_qitech (catalogo de dias com publicacao QiTech)

Cria a tabela `wh_dia_util_qitech` e popula com backfill inferido de
`wh_mec_evolucao_cotas` (fonte-pulse: presenca de MEC implica que a QiTech
publicou o snapshot do fundo naquele dia).

Decisao 2026-05-07 (sessao com usuario): MEC e a referencia unica para Fase
A. Outras tabelas analiticas podem ter ausencias legitimas (fundo sem RF,
sem compromissada) que NAO distorcem o conceito de dia util.

Revision ID: f9a3c2b1d8e0
Revises: e8c4f7a2b1d3
Create Date: 2026-05-07 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9a3c2b1d8e0"
down_revision: str | None = "e8c4f7a2b1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Criar a tabela.
    op.create_table(
        "wh_dia_util_qitech",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "unidade_administrativa_id", sa.UUID(), nullable=False
        ),
        sa.Column("data_posicao", sa.Date(), nullable=False),
        sa.Column(
            "source_type",
            sa.String(length=64),
            server_default=sa.text("'admin:qitech'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'completo'"),
            nullable=False,
        ),
        sa.Column("relatorios_esperados", sa.Integer(), nullable=True),
        sa.Column("relatorios_recebidos", sa.Integer(), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "ingested_by_version", sa.String(length=128), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["unidade_administrativa_id"],
            ["cadastros_unidade_administrativa.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "unidade_administrativa_id",
            "data_posicao",
            "source_type",
            name="uq_wh_dia_util_qitech",
        ),
    )
    op.create_index(
        op.f("ix_wh_dia_util_qitech_tenant_id"),
        "wh_dia_util_qitech",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_dia_util_qitech_data_posicao"),
        "wh_dia_util_qitech",
        ["data_posicao"],
        unique=False,
    )
    op.create_index(
        "ix_wh_dia_util_qitech_busca",
        "wh_dia_util_qitech",
        ["tenant_id", "unidade_administrativa_id", "data_posicao"],
        unique=False,
    )

    # 2) Backfill via DISTINCT em wh_mec_evolucao_cotas.
    #    Filtra ua_id IS NOT NULL pq a tabela nova exige ua_id NOT NULL
    #    (e linhas legacy de MEC podem ter ua nulo — sao ignoradas no
    #    backfill, ETL Fase B preenche se for o caso).
    op.execute(
        """
        INSERT INTO wh_dia_util_qitech (
            tenant_id,
            unidade_administrativa_id,
            data_posicao,
            source_type,
            status,
            ingested_at,
            ingested_by_version
        )
        SELECT DISTINCT
            tenant_id,
            unidade_administrativa_id,
            data_posicao,
            'admin:qitech',
            'completo',
            now(),
            'backfill_v1.0.0'
        FROM wh_mec_evolucao_cotas
        WHERE unidade_administrativa_id IS NOT NULL
        ON CONFLICT (tenant_id, unidade_administrativa_id, data_posicao, source_type)
        DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wh_dia_util_qitech_busca", table_name="wh_dia_util_qitech"
    )
    op.drop_index(
        op.f("ix_wh_dia_util_qitech_data_posicao"),
        table_name="wh_dia_util_qitech",
    )
    op.drop_index(
        op.f("ix_wh_dia_util_qitech_tenant_id"),
        table_name="wh_dia_util_qitech",
    )
    op.drop_table("wh_dia_util_qitech")
