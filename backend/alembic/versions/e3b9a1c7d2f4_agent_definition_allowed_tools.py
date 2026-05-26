"""agent_definition: coluna allowed_tools (override de tools sem deploy)

Torna a SELECAO de tools de um agente editavel como dado (CLAUDE.md
§19.0/§19.12), removendo a necessidade de editar `SpecialistAgentSpec.tools`
no codigo + deploy para retunar o conjunto de tools de um agente existente.

Coluna `allowed_tools` (ARRAY de text, nullable) em `agent_definition`.
Semantica do valor (resolvida no runtime via `ToolRegistry.get_available`):
    NULL  -> usa o default do CATALOG (`SpecialistAgentSpec.tools`).
             Preserva o comportamento de TODOS os agentes ja seedados —
             nenhum backfill necessario.
    []    -> agente sem tools (conversacional puro / explicito).
    [...] -> override explicito (nomes literais ou wildcard "<modulo>.*").

Sem FK (lista de strings). Sem backfill: deixar NULL mantem a fonte de
verdade no CATALOG ate alguem sobrescrever pela UI.

Revision ID: e3b9a1c7d2f4
Revises: c7d9e1f3a5b8
Create Date: 2026-05-26
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "e3b9a1c7d2f4"
down_revision = "c7d9e1f3a5b8"
branch_labels = None
depends_on = None

_TABLE = "agent_definition"
_COLUMN = "allowed_tools"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, postgresql.ARRAY(sa.String()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, _COLUMN)
