"""warehouse_wh_liquidacao

Revision ID: e8b3c6a1d9f4
Revises: b5d7e2a9c4f1
Create Date: 2026-07-07

F3 do programa antifraude: silver canonico `wh_liquidacao` — eventos de
desfecho DECLARADO por titulo (visao Bitfin; futuras fontes entram na mesma
tabela com outro source_type). Grao = evento; business key tenant+source_id
prefixado por tipo (liq:/rec:/tra:/man:/bxa:/per:). Ver
app/warehouse/liquidacao.py.

Tambem faz o seed TSEC do endpoint `bitfin.liquidacoes` (interval 360)
espelhando cada linha `bitfin.full_sync` existente (padrao c7d9e1f3a5b8).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e8b3c6a1d9f4"
down_revision: str | Sequence[str] | None = "b5d7e2a9c4f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _auditable_cols() -> list[sa.Column]:
    return [
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
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


def upgrade() -> None:
    op.create_table(
        "wh_liquidacao",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("titulo_id", sa.Integer(), nullable=False),
        sa.Column("operacao_id", sa.Integer(), nullable=True),
        sa.Column("unidade_administrativa_id", sa.Integer(), nullable=True),
        sa.Column("canal", sa.String(24), nullable=False),
        sa.Column("evidencia", sa.String(24), nullable=True),
        sa.Column("meio_codigo", sa.String(4), nullable=True),
        sa.Column("data_evento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_credito", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valor_pago", sa.Numeric(18, 4), nullable=True),
        sa.Column("valor_titulo", sa.Numeric(18, 4), nullable=True),
        sa.Column("juros", sa.Numeric(18, 4), nullable=True),
        sa.Column("agencia_id", sa.Integer(), nullable=True),
        sa.Column("local_pagamento", sa.String(255), nullable=True),
        sa.Column("pago_fora_praca_sacado", sa.Boolean(), nullable=True),
        sa.Column("pago_na_praca_cliente", sa.Boolean(), nullable=True),
        sa.Column("pago_na_agencia_cliente", sa.Boolean(), nullable=True),
        sa.Column("pago_na_agencia_sacado", sa.Boolean(), nullable=True),
        sa.Column("pago_em_banco_digital", sa.Boolean(), nullable=True),
        sa.Column("registrado", sa.Boolean(), nullable=True),
        sa.Column("carteira_bancaria_id", sa.Integer(), nullable=True),
        sa.Column("recompra_id", sa.Integer(), nullable=True),
        sa.Column("situacao_titulo", sa.Integer(), nullable=False),
        *_auditable_cols(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "source_id", name="uq_wh_liquidacao"),
    )
    for col in (
        "tenant_id",
        "titulo_id",
        "operacao_id",
        "unidade_administrativa_id",
        "canal",
        "evidencia",
        "data_evento",
        "recompra_id",
    ):
        op.create_index(
            op.f(f"ix_wh_liquidacao_{col}"), "wh_liquidacao", [col]
        )

    # Seed TSEC do endpoint novo, espelhando cada linha bitfin.full_sync.
    op.execute(
        sa.text(
            "INSERT INTO tenant_source_endpoint_config "
            "(id, tenant_id, source_type, environment, "
            " unidade_administrativa_id, endpoint_name, enabled, "
            " schedule_kind, schedule_value, created_at, updated_at) "
            "SELECT gen_random_uuid(), tenant_id, source_type, environment, "
            "       unidade_administrativa_id, 'bitfin.liquidacoes', true, "
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
            "WHERE endpoint_name = 'bitfin.liquidacoes'"
        )
    )
    for col in (
        "recompra_id",
        "data_evento",
        "evidencia",
        "canal",
        "unidade_administrativa_id",
        "operacao_id",
        "titulo_id",
        "tenant_id",
    ):
        op.drop_index(op.f(f"ix_wh_liquidacao_{col}"), table_name="wh_liquidacao")
    op.drop_table("wh_liquidacao")
