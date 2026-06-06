"""wh_cobranca_sync_run: rastreamento de execucoes do sync manual de cobranca

Cada clique no botao "Sincronizar" cria uma linha; o subprocess atualiza a fase
(heartbeat) e marca status/finished_at. Responde "travou?" e "ultima sync?".

Revision ID: b8d2f4a6c1e3
Revises: e7f2a3c8b1d9
Create Date: 2026-06-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "b8d2f4a6c1e3"
down_revision: str | None = "e7f2a3c8b1d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wh_cobranca_sync_run",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("fase", sa.String(12), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arquivos_vistos", sa.Integer(), nullable=True),
        sa.Column("arquivos_novos", sa.Integer(), nullable=True),
        sa.Column("boletos_ativos", sa.Integer(), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_wh_cobranca_sync_run_tenant_id",
        "wh_cobranca_sync_run",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_cobranca_sync_run_tenant_started",
        "wh_cobranca_sync_run",
        ["tenant_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wh_cobranca_sync_run_tenant_started",
        table_name="wh_cobranca_sync_run",
    )
    op.drop_index(
        "ix_wh_cobranca_sync_run_tenant_id", table_name="wh_cobranca_sync_run"
    )
    op.drop_table("wh_cobranca_sync_run")
