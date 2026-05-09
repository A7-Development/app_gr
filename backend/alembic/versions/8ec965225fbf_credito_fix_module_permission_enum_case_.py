"""credito: fix module/permission enum case (lowercase to uppercase)

Revision ID: 8ec965225fbf
Revises: 855c33dfd7df
Create Date: 2026-05-01 14:21:49.555949

Bug-fix da migration `855c33dfd7df`: o `SAEnum` do SQLAlchemy armazena o
**nome** do enum (uppercase) no banco quando `native_enum=False`, nao o
`.value`. Inserimos 'credito' (value) ao inves de 'CREDITO' (name), o que
quebrava a desserializacao em `auth.py::me` com:

    LookupError: 'credito' is not among the defined enum values.
    Enum name: module. Possible values: BI, CADASTROS, ..., ADMIN

Mesmo problema com 'admin' -> 'ADMIN' em `user_module_permission`.

Esta migration corrige os dados existentes via UPDATE direto. Para novas
instalacoes, a migration `855c33dfd7df` foi tambem atualizada para usar
uppercase desde o inicio (apesar de nao re-rodar para installs ja
executadas).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ec965225fbf"
down_revision: str | None = "855c33dfd7df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fix tenant_module_subscription: 'credito' -> 'CREDITO'
    op.execute(
        sa.text(
            "UPDATE tenant_module_subscription "
            "SET module = 'CREDITO', updated_at = now() "
            "WHERE module = 'credito'"
        )
    )

    # Fix user_module_permission: 'credito' -> 'CREDITO'
    op.execute(
        sa.text(
            "UPDATE user_module_permission "
            "SET module = 'CREDITO', updated_at = now() "
            "WHERE module = 'credito'"
        )
    )

    # Fix permission column too (lowercase 'admin' -> uppercase 'ADMIN')
    op.execute(
        sa.text(
            "UPDATE user_module_permission "
            "SET permission = 'ADMIN', updated_at = now() "
            "WHERE module = 'CREDITO' AND permission = 'admin'"
        )
    )


def downgrade() -> None:
    # Reverter para o estado bugado (lowercase) — apenas para reverter
    # esta migration sem perda de informacao. Em pratica nao se usa.
    op.execute(
        sa.text(
            "UPDATE tenant_module_subscription "
            "SET module = 'credito' WHERE module = 'CREDITO'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE user_module_permission "
            "SET module = 'credito' WHERE module = 'CREDITO'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE user_module_permission "
            "SET permission = 'admin' WHERE module = 'credito' AND permission = 'ADMIN'"
        )
    )
