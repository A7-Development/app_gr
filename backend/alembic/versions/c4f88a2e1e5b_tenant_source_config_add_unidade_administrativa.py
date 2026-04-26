"""integracoes: tenant_source_config ganha unidade_administrativa_id (multi-UA)

Revision ID: c4f88a2e1e5b
Revises: 733528384336
Create Date: 2026-04-25 18:00:00.000000

Phase F — multi-UA QiTech (CLAUDE.md secao 13). Habilita um tenant ter N
credenciais para o mesmo source_type, uma por UA (ex.: 2 FIDCs no QiTech).

Mudancas:
    1. ADD COLUMN tenant_source_config.unidade_administrativa_id UUID NULL
       FK -> cadastros_unidade_administrativa(id) ON DELETE RESTRICT.
       Index pra lookup por UA.
    2. Backfill: para cada linha existente, vincula a UA do tenant (preferencia
       FIDC ativa mais antiga; fallback: 1a UA ativa criada). Tenants sem UA
       cadastrada permanecem com NULL — a aplicacao recusa novas inserts sem
       UA, mas linhas legacy continuam funcionais.
    3. Drop UQ antiga (tenant, source_type, environment) e cria nova UQ que
       inclui unidade_administrativa_id. PG trata cada NULL como distinto,
       entao linhas legacy NAO bloqueiam upserts de novas linhas com UA.

Downgrade: drop nova UQ + restaura UQ antiga + drop coluna. Retrocompat e
total porque a coluna era nullable e a UQ antiga era subset da nova.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f88a2e1e5b"
down_revision: str | None = "733528384336"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. ADD COLUMN
    op.add_column(
        "tenant_source_config",
        sa.Column(
            "unidade_administrativa_id",
            PG_UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_tenant_source_config_ua",
        "tenant_source_config",
        "cadastros_unidade_administrativa",
        ["unidade_administrativa_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_tenant_source_config_ua",
        "tenant_source_config",
        ["unidade_administrativa_id"],
    )

    # 2. Backfill: 1 UA por tenant (FIDC ativa mais antiga, com fallback).
    # DISTINCT ON pega a 1a linha por tenant_id apos o ORDER BY:
    #   - ativa = true antes de inativa
    #   - tipo FIDC antes de outros (regra de negocio: integracao QiTech
    #     hoje so faz sentido pra FIDC; futuramente outros tipos podem
    #     assinar, ai esse default vira ambiguo e precisara de override
    #     manual — aceitavel porque ainda e single-UA-por-config).
    #   - created_at ASC pra estabilidade (a 1a UA cadastrada vence).
    op.execute(
        sa.text(
            """
            UPDATE tenant_source_config tsc
            SET unidade_administrativa_id = sub.ua_id
            FROM (
                SELECT DISTINCT ON (tenant_id)
                    tenant_id,
                    id AS ua_id
                FROM cadastros_unidade_administrativa
                ORDER BY
                    tenant_id,
                    ativa DESC,
                    (tipo = 'FIDC') DESC,
                    created_at ASC
            ) sub
            WHERE tsc.tenant_id = sub.tenant_id
              AND tsc.unidade_administrativa_id IS NULL
            """
        )
    )

    # 3. Rotaciona unique constraint
    op.drop_constraint(
        "uq_tenant_source_env", "tenant_source_config", type_="unique"
    )
    op.create_unique_constraint(
        "uq_tenant_source_env_ua",
        "tenant_source_config",
        ["tenant_id", "source_type", "environment", "unidade_administrativa_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_tenant_source_env_ua", "tenant_source_config", type_="unique"
    )
    op.create_unique_constraint(
        "uq_tenant_source_env",
        "tenant_source_config",
        ["tenant_id", "source_type", "environment"],
    )
    op.drop_index(
        "ix_tenant_source_config_ua", table_name="tenant_source_config"
    )
    op.drop_constraint(
        "fk_tenant_source_config_ua",
        "tenant_source_config",
        type_="foreignkey",
    )
    op.drop_column("tenant_source_config", "unidade_administrativa_id")
