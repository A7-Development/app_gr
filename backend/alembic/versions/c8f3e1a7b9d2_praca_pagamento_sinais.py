"""sinais de praca de pagamento (risco de autoliquidacao/lastro frio)

1. wh_posicao_sacado += 4 totais de praca (fora da praca do sacado / praca
   do cliente / agencia do cliente / banco digital).
2. wh_posicao_sacado_cedente — relacao sacado x cedente (SacadoPosicaoCliente)
   com risco, recompras e os 4 sinais de praca. Divergencia concentrada num
   unico cedente = desenho classico de autoliquidacao.
3. wh_pagamento_praca_mensal — serie mensal por conta operacional/cedente
   (PosicaoHistoricaPagamentoPraca, 5 buckets, desde 2022-01). Tendencia.

Revision ID: c8f3e1a7b9d2
Revises: f4a8c2e9b1d7
Create Date: 2026-06-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c8f3e1a7b9d2"
down_revision: str | Sequence[str] | None = "f4a8c2e9b1d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRACA_COLS = (
    "pagamentos_fora_praca_sacado",
    "pagamentos_praca_cliente",
    "pagamentos_agencia_cliente",
    "pagamentos_banco_digital",
)


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
    # 1. Totais de praca no consolidado do sacado
    for col in _PRACA_COLS:
        op.add_column(
            "wh_posicao_sacado", sa.Column(col, sa.Numeric(18, 4), nullable=True)
        )

    # 2. Relacao sacado x cedente
    op.create_table(
        "wh_posicao_sacado_cedente",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("entidade_id", sa.UUID(), nullable=True),
        sa.Column("papel_source_id", sa.String(length=64), nullable=False),
        sa.Column("cedente_entidade_id", sa.UUID(), nullable=True),
        sa.Column("cedente_papel_source_id", sa.String(length=64), nullable=True),
        sa.Column("conta_operacional_source_id", sa.Integer(), nullable=False),
        sa.Column("ticket_medio", sa.Numeric(18, 4), nullable=True),
        sa.Column("indice_liquidez", sa.Numeric(10, 4), nullable=True),
        sa.Column("hist_recompras_qtd", sa.Integer(), nullable=True),
        sa.Column("hist_recompras_valor", sa.Numeric(18, 4), nullable=True),
        *[sa.Column(c, sa.Numeric(18, 4), nullable=True) for c in _PRACA_COLS],
        sa.Column("risco_total_qtd", sa.Integer(), nullable=True),
        sa.Column("risco_total_valor", sa.Numeric(18, 4), nullable=True),
        sa.Column("risco_vencido_qtd", sa.Integer(), nullable=True),
        sa.Column("risco_vencido_valor", sa.Numeric(18, 4), nullable=True),
        sa.Column("risco_avencer_qtd", sa.Integer(), nullable=True),
        sa.Column("risco_avencer_valor", sa.Numeric(18, 4), nullable=True),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entidade_id"], ["wh_entidade.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["cedente_entidade_id"], ["wh_entidade.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_type", "source_id",
            name="uq_wh_posicao_sacado_cedente",
        ),
    )
    op.create_index(
        op.f("ix_wh_posicao_sacado_cedente_tenant_id"),
        "wh_posicao_sacado_cedente", ["tenant_id"], unique=False,
    )
    op.create_index(
        "ix_wh_pos_sac_ced_sacado",
        "wh_posicao_sacado_cedente", ["tenant_id", "entidade_id"], unique=False,
    )
    op.create_index(
        "ix_wh_pos_sac_ced_cedente",
        "wh_posicao_sacado_cedente",
        ["tenant_id", "cedente_entidade_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_posicao_sacado_cedente_papel_source_id"),
        "wh_posicao_sacado_cedente", ["papel_source_id"], unique=False,
    )
    op.create_index(
        op.f("ix_wh_posicao_sacado_cedente_cedente_papel_source_id"),
        "wh_posicao_sacado_cedente", ["cedente_papel_source_id"], unique=False,
    )

    # 3. Serie mensal de praca
    op.create_table(
        "wh_pagamento_praca_mensal",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("cedente_entidade_id", sa.UUID(), nullable=True),
        sa.Column("cedente_papel_source_id", sa.String(length=64), nullable=True),
        sa.Column("conta_operacional_source_id", sa.Integer(), nullable=False),
        sa.Column("ano", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("pago_na_praca_sacado", sa.Numeric(18, 4), nullable=True),
        sa.Column("pago_fora_praca_sacado", sa.Numeric(18, 4), nullable=True),
        sa.Column("pago_na_praca_cliente", sa.Numeric(18, 4), nullable=True),
        sa.Column("pago_na_agencia_cliente", sa.Numeric(18, 4), nullable=True),
        sa.Column("pago_em_banco_digital", sa.Numeric(18, 4), nullable=True),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["cedente_entidade_id"], ["wh_entidade.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_type", "source_id",
            name="uq_wh_pagamento_praca_mensal",
        ),
    )
    op.create_index(
        op.f("ix_wh_pagamento_praca_mensal_tenant_id"),
        "wh_pagamento_praca_mensal", ["tenant_id"], unique=False,
    )
    op.create_index(
        "ix_wh_pag_praca_cedente_mes",
        "wh_pagamento_praca_mensal",
        ["tenant_id", "cedente_entidade_id", "ano", "mes"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_pagamento_praca_mensal_cedente_papel_source_id"),
        "wh_pagamento_praca_mensal", ["cedente_papel_source_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_table("wh_pagamento_praca_mensal")
    op.drop_table("wh_posicao_sacado_cedente")
    for col in reversed(_PRACA_COLS):
        op.drop_column("wh_posicao_sacado", col)
