"""integracoes: backfill_job table for async date-range backfill

Cria a tabela `backfill_job` que coordena execucao assincrona de backfill
de furos historicos. 1 job = 1 endpoint x N datas (granularidade fina por
endpoint, ver project_qitech_freshness_followups memory).

Worker em APScheduler (`app/scheduler/jobs/backfill_worker.py`) polla a
tabela a cada 5s, pega 1 job `pending`, processa as datas em serie
chamando `run_sync_endpoint(since=date)` pra cada uma.

Mescla 2 heads pre-existentes (cosif + dre_classification_rule).

Revision ID: d2a8e4f1b3c7
Revises: ('7f1a9c4e2d83', 'c1e7b2a4d5f3')
Create Date: 2026-05-12 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d2a8e4f1b3c7"
down_revision: str | tuple[str, ...] | None = ("7f1a9c4e2d83", "c1e7b2a4d5f3")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backfill_job",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column(
            "unidade_administrativa_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("endpoint_name", sa.String(128), nullable=False),
        sa.Column(
            "dates_pending",
            postgresql.ARRAY(sa.Date),
            nullable=False,
        ),
        sa.Column(
            "dates_done",
            postgresql.ARRAY(sa.Date),
            nullable=False,
            server_default=sa.text("'{}'::date[]"),
        ),
        sa.Column(
            "dates_failed",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed', 'cancelled')",
            name="ck_backfill_job_status",
        ),
    )
    op.create_index(
        "ix_backfill_job_tenant_status",
        "backfill_job",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_backfill_job_endpoint",
        "backfill_job",
        ["tenant_id", "source_type", "endpoint_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_backfill_job_endpoint", table_name="backfill_job")
    op.drop_index("ix_backfill_job_tenant_status", table_name="backfill_job")
    op.drop_table("backfill_job")
