"""credito: fix workflow_definition.graph stored as JSON string (parse to object)

Revision ID: 4dfbd64002b5
Revises: 8ec965225fbf
Create Date: 2026-05-01 14:27:42.534877

Bug-fix das migrations `cbe3af2c3bf5` (workflow A7 v1) e `e70618ebe077`
(workflow A7 v2): chamamos `json.dumps(GRAPH)` antes de `op.bulk_insert`,
o que armazenou o JSONB como uma STRING serializada em vez de um objeto.

Como resultado, `jsonb_typeof(graph) = 'string'` e o Pydantic explodia
ao validar `WorkflowDefinitionRead.graph: dict` com erro:

    pydantic_core.ValidationError: 1 validation error for WorkflowDefinitionRead
    graph
      Input should be a valid dictionary [type=dict_type, input_value='{...}']

Esta migration faz `UPDATE` extraindo a string interna e re-castando como
JSONB-objeto via `(graph #>> '{}')::jsonb`. As migrations originais foram
tambem corrigidas para nao chamar `json.dumps` em novas instalacoes.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4dfbd64002b5"
down_revision: str | None = "8ec965225fbf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `graph #>> '{}'` extrai a string crua armazenada (sem o wrap JSON);
    # depois fazemos o cast pra JSONB para obter o objeto correto.
    # WHERE: so toca rows que estao no estado bugado (jsonb_typeof = 'string').
    op.execute(
        sa.text(
            """
            UPDATE workflow_definition
            SET graph = (graph #>> '{}')::jsonb
            WHERE jsonb_typeof(graph) = 'string'
            """
        )
    )


def downgrade() -> None:
    # Re-serializa de volta para string (estado bugado original).
    # Util apenas para reverter esta migration; nao se usa em pratica.
    op.execute(
        sa.text(
            """
            UPDATE workflow_definition
            SET graph = to_jsonb(graph::text)
            WHERE jsonb_typeof(graph) = 'object'
            """
        )
    )
