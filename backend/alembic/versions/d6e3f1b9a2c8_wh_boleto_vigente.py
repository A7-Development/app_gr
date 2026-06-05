"""wh_boleto_vigente: estado vigente do boleto (projecao do fold)

Fatia 3 do rebuild. Tabela do estado corrente do boleto (1 linha por boleto),
projetada do fold de wh_boleto_evento. Aditiva: nao toca wh_boleto antigo
(cutover so na Fatia 4). Ver app/warehouse/boleto_vigente.py.

Revision ID: d6e3f1b9a2c8
Revises: c5d9e2a1f7b4
Create Date: 2026-06-05

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision: str = "d6e3f1b9a2c8"
down_revision: str | None = "c5d9e2a1f7b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _has_table("wh_boleto_vigente"):
        return
    op.create_table(
        "wh_boleto_vigente",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("banco_origem", sa.String(length=20), nullable=False),
        sa.Column("ua_id", sa.Integer(), nullable=True),
        sa.Column("ua_nome", sa.String(length=200), nullable=True),
        sa.Column("nosso_numero", sa.String(length=50), nullable=False),
        sa.Column("numero_documento", sa.String(length=50), nullable=False),
        sa.Column("sacado_documento", sa.String(length=20), nullable=True),
        sa.Column("sacado_nome", sa.String(length=255), nullable=True),
        sa.Column("estado", sa.String(length=12), nullable=False),
        sa.Column("valor_atual", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("data_vencimento", sa.Date(), nullable=True),
        sa.Column("valor_pago", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("data_pagamento", sa.Date(), nullable=True),
        sa.Column("tipo_evento_vigente", sa.String(length=40), nullable=False),
        sa.Column("codigo_ocorrencia_vigente", sa.String(length=10), nullable=True),
        sa.Column("data_ocorrencia_vigente", sa.Date(), nullable=False),
        sa.Column("primeiro_evento_em", sa.Date(), nullable=True),
        sa.Column("n_eventos", sa.Integer(), nullable=False),
        sa.Column("projected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("projected_by_version", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "banco_origem", "nosso_numero", name="uq_wh_boleto_vigente"
        ),
    )
    op.create_index(
        op.f("ix_wh_boleto_vigente_tenant_id"),
        "wh_boleto_vigente",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_wh_boleto_vigente_cruzamento",
        "wh_boleto_vigente",
        ["tenant_id", "banco_origem", "estado", "numero_documento"],
        unique=False,
    )
    op.create_index(
        "ix_wh_boleto_vigente_ua_estado",
        "wh_boleto_vigente",
        ["tenant_id", "ua_id", "estado"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wh_boleto_vigente_ua_estado", table_name="wh_boleto_vigente"
    )
    op.drop_index(
        "ix_wh_boleto_vigente_cruzamento", table_name="wh_boleto_vigente"
    )
    op.drop_index(
        op.f("ix_wh_boleto_vigente_tenant_id"), table_name="wh_boleto_vigente"
    )
    op.drop_table("wh_boleto_vigente")
