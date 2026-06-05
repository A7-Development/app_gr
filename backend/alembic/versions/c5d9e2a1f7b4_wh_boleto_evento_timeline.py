"""wh_boleto_evento: timeline de eventos do boleto (silver)

Fatia 1 do rebuild da carteira de cobranca (conciliacao estado-vs-estado).
Cria a timeline append-only de eventos decodificados do CNAB -- fonte da
verdade da qual o estado vigente do boleto e uma projecao (fold).

Aditivo: nao toca wh_boleto (modelo antigo por data_ref continua vivo ate o
cutover da Fatia 4). Ver CLAUDE.md secao 13.2 (bronze->silver) e 14 (timeline
auditavel).

Revision ID: c5d9e2a1f7b4
Revises: 39f86beb8fd0
Create Date: 2026-06-05

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision: str = "c5d9e2a1f7b4"
down_revision: str | None = "39f86beb8fd0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _has_table("wh_boleto_evento"):
        return
    op.create_table(
        "wh_boleto_evento",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("banco_origem", sa.String(length=20), nullable=False),
        sa.Column("ua_id", sa.Integer(), nullable=True),
        sa.Column("ua_nome", sa.String(length=200), nullable=True),
        sa.Column("nosso_numero", sa.String(length=50), nullable=False),
        sa.Column("numero_documento", sa.String(length=50), nullable=False),
        sa.Column("sacado_documento", sa.String(length=20), nullable=True),
        sa.Column("sacado_nome", sa.String(length=255), nullable=True),
        sa.Column("codigo_ocorrencia", sa.String(length=10), nullable=False),
        sa.Column("tipo_evento", sa.String(length=40), nullable=False),
        sa.Column("efeito_estado", sa.String(length=12), nullable=False),
        sa.Column("data_ocorrencia", sa.Date(), nullable=False),
        sa.Column("data_vencimento", sa.Date(), nullable=True),
        sa.Column("valor_titulo", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("valor_pago", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("data_pagamento", sa.Date(), nullable=True),
        sa.Column("origem", sa.String(length=12), nullable=False),
        sa.Column("arquivo_id", sa.UUID(), nullable=False),
        sa.Column("ocorrencia_id", sa.UUID(), nullable=False),
        sa.Column("decoded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decoded_by_version", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["arquivo_id"], ["wh_cnab_raw_arquivo.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["ocorrencia_id"], ["wh_cnab_raw_ocorrencia.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "ocorrencia_id", name="uq_wh_boleto_evento_ocorrencia"
        ),
    )
    op.create_index(
        op.f("ix_wh_boleto_evento_tenant_id"),
        "wh_boleto_evento",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_wh_boleto_evento_fold",
        "wh_boleto_evento",
        ["tenant_id", "banco_origem", "nosso_numero", "data_ocorrencia"],
        unique=False,
    )
    op.create_index(
        "ix_wh_boleto_evento_ua",
        "wh_boleto_evento",
        ["tenant_id", "ua_id"],
        unique=False,
    )
    op.create_index(
        "ix_wh_boleto_evento_numero",
        "wh_boleto_evento",
        ["tenant_id", "numero_documento"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_wh_boleto_evento_numero", table_name="wh_boleto_evento")
    op.drop_index("ix_wh_boleto_evento_ua", table_name="wh_boleto_evento")
    op.drop_index("ix_wh_boleto_evento_fold", table_name="wh_boleto_evento")
    op.drop_index(
        op.f("ix_wh_boleto_evento_tenant_id"), table_name="wh_boleto_evento"
    )
    op.drop_table("wh_boleto_evento")
