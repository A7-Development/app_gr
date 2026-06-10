"""merge heads drop_dre_natureza + serasa_liminar

Revision ID: 2e4aa7fef995
Revises: a8c4e1f7b9d2, a8e4c2f6b1d3
Create Date: 2026-06-10 20:13:03.817360

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e4aa7fef995'
down_revision: str | None = ('a8c4e1f7b9d2', 'a8e4c2f6b1d3')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
