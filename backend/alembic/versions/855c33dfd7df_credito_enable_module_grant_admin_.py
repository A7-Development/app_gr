"""credito: enable module + grant admin permission to existing tenants and users

Revision ID: 855c33dfd7df
Revises: 469fa975077a
Create Date: 2026-05-01 14:17:31.907234

Habilita o modulo CREDITO para TODOS os tenants existentes e concede
permissao ADMIN no CREDITO para TODOS os usuarios existentes. Idempotente
via ON CONFLICT DO NOTHING (Postgres).

Necessario porque o backend so registrou as rotas — sem subscription o
`require_module` devolve HTTP 402 Payment Required. No futuro, habilitar
modulo para um novo tenant sera via UI de admin global; por ora seedamos
para destravar o desenvolvimento.

NOTE: o downgrade NAO desabilita os modulos para nao quebrar dossies
existentes. Reverter manualmente via SQL se necessario.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "855c33dfd7df"
down_revision: str | None = "469fa975077a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # IMPORTANTE: SAEnum com `native_enum=False` armazena o NAME do enum
    # (CREDITO, ADMIN, etc.) — uppercase. Usar value lowercase quebra a
    # desserializacao na ORM. Os outros modulos (BI, CADASTROS, ...) ja
    # estao em uppercase no banco — segue a mesma convencao.

    # 1. Habilita CREDITO para todos os tenants existentes.
    # ON CONFLICT: se ja existe a row (tenant + module), atualiza para enabled=true.
    op.execute(
        sa.text(
            """
            INSERT INTO tenant_module_subscription
                (tenant_id, module, enabled, enabled_since, created_at, updated_at)
            SELECT
                t.id, 'CREDITO', true, now(), now(), now()
            FROM tenants t
            ON CONFLICT (tenant_id, module) DO UPDATE
                SET enabled = true,
                    enabled_since = COALESCE(tenant_module_subscription.enabled_since, now()),
                    updated_at = now()
            """
        )
    )

    # 2. Concede ADMIN no CREDITO para todos os usuarios existentes.
    # Onda 1: simples — todo user vira admin do credito. Em prod, isso vai
    # ser controlado pela UI de gestao de usuarios.
    op.execute(
        sa.text(
            """
            INSERT INTO user_module_permission
                (user_id, module, permission, created_at, updated_at)
            SELECT
                u.id, 'CREDITO', 'ADMIN', now(), now()
            FROM users u
            ON CONFLICT (user_id, module) DO UPDATE
                SET permission = 'ADMIN',
                    updated_at = now()
            """
        )
    )


def downgrade() -> None:
    # Soft revert — desabilita subscription mas mantem rows para auditoria.
    op.execute(
        sa.text(
            "UPDATE tenant_module_subscription SET enabled = false, updated_at = now() "
            "WHERE module = 'CREDITO'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE user_module_permission SET permission = 'NONE', updated_at = now() "
            "WHERE module = 'CREDITO'"
        )
    )
