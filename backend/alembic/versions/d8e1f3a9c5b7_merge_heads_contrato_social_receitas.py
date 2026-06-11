"""merge heads: contrato social (b7d2e9f4a1c3) + linha receitas (c8f3e1a7b9d2)

Sessões paralelas criaram migrations a partir do mesmo ancestral
(a9c4e7f1b2d8), divergindo os heads. Merge revision no-op — só junta as
linhas pra `alembic upgrade head` voltar a resolver sem ambiguidade.

Revision ID: d8e1f3a9c5b7
Revises: b7d2e9f4a1c3, c8f3e1a7b9d2
Create Date: 2026-06-11
"""
from collections.abc import Sequence

revision: str = "d8e1f3a9c5b7"
down_revision: str | Sequence[str] | None = ("b7d2e9f4a1c3", "c8f3e1a7b9d2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
