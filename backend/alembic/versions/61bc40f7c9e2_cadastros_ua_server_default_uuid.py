"""cadastros: ua server_default uuid

Adiciona `DEFAULT gen_random_uuid()` na coluna `id` da
`cadastros_unidade_administrativa`. Permite INSERT direto via SQL bruto /
MCP / scripts de bootstrap sem precisar gerar UUID na aplicacao.

ORM continua usando `default=uuid4` Python-side (mais rapido — evita
round-trip pro DB). O server_default e fallback pra escritas que nao
passam pelo ORM.

Revision ID: 61bc40f7c9e2
Revises: 40c76a6cec65
Create Date: 2026-04-25 12:09:35.126927
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "61bc40f7c9e2"
down_revision: str | None = "40c76a6cec65"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "cadastros_unidade_administrativa",
        "id",
        server_default=sa.text("gen_random_uuid()"),
    )


def downgrade() -> None:
    op.alter_column(
        "cadastros_unidade_administrativa",
        "id",
        server_default=None,
    )
