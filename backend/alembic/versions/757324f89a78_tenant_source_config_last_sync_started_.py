"""tenant_source_config_last_sync_started_at

Revision ID: 757324f89a78
Revises: 7e003b3b1e53
Create Date: 2026-05-05 09:45:04.453012

Why: o `sync_dispatcher` decidia "passou o intervalo?" lendo `last_sync_attempt_at`
do `decision_log`, que so e gravado no FIM do ciclo. Sync que demorava mais que
`sync_frequency_minutes` causava reentrada — cada tick subsequente disparava nova
sync em paralelo, saturando o thread pool. Com timeouts ausentes no pyodbc e
`fetchall()` materializando tabelas inteiras, isso virava deadlock no
`executor.shutdown(wait=True)` durante reload do uvicorn.

Esta coluna registra o `started_at` de cada sync ANTES de chamar `adapter.sync`.
O dispatcher passa a considerar `MAX(last_sync_started_at, last_sync_attempt_at)`
como "ultimo evento" para fins de cadencia.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "757324f89a78"
down_revision: str | None = "7e003b3b1e53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_source_config",
        sa.Column(
            "last_sync_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_source_config", "last_sync_started_at")
