"""merge heads: bdc (a1c4e7f2b9d3) + concilia_boletos (b7e1c3a9f2d4)

Revision ID: 39f86beb8fd0
Revises: a1c4e7f2b9d3, b7e1c3a9f2d4
Create Date: 2026-06-04 17:11:06.300033

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '39f86beb8fd0'
down_revision: str | None = ('a1c4e7f2b9d3', 'b7e1c3a9f2d4')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
