"""merge heads grupo_receita + paralela

Revision ID: 4d58236581fa
Revises: e8b3c5f1a7d2, a3c7e1f5b9d2
Create Date: 2026-06-11 20:44:10.524056

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d58236581fa'
down_revision: str | None = ('e8b3c5f1a7d2', 'a3c7e1f5b9d2')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
