"""agent_config: per-agent model override (system maintainer editavel)

Revision ID: a4f7e2c8b1d5
Revises: f3a8b9d2c1e4
Create Date: 2026-05-02 17:00:00.000000

Cria tabela `agent_config` que permite ao mantenedor escolher o modelo
Anthropic de cada Specialist Agent (etapa 1 — provider fixo Anthropic).
Seed inicial replica os valores hardcoded em
`app.shared.agents.catalog.CATALOG` para que comportamento nao mude
imediatamente apos a migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a4f7e2c8b1d5"
down_revision: str | None = "f3a8b9d2c1e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SEED = [
    # (agent_name, model, fallback_model)
    ("social_contract_analyst", "claude-opus-4-5", "claude-sonnet-4-5"),
    ("financial_analyst", "claude-opus-4-5", "claude-sonnet-4-5"),
    ("indebtedness_analyst", "claude-opus-4-5", "claude-sonnet-4-5"),
    ("legal_analyst", "claude-opus-4-5", "claude-sonnet-4-5"),
    ("partner_analyst", "claude-opus-4-5", "claude-sonnet-4-5"),
    ("commercial_visit_analyst", "claude-opus-4-5", "claude-sonnet-4-5"),
    ("cross_reference_analyst", "claude-opus-4-5", "claude-sonnet-4-5"),
    ("opinion_writer", "claude-opus-4-5", "claude-sonnet-4-5"),
    ("document_extractor", "claude-opus-4-5", "claude-sonnet-4-5"),
    ("pleito_extractor", "claude-haiku-4-5-20251001", None),
]


def upgrade() -> None:
    op.create_table(
        "agent_config",
        sa.Column("agent_name", sa.String(length=64), primary_key=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("fallback_model", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_by_user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )

    table = sa.table(
        "agent_config",
        sa.column("agent_name", sa.String),
        sa.column("model", sa.String),
        sa.column("fallback_model", sa.String),
    )
    op.bulk_insert(
        table,
        [
            {"agent_name": name, "model": model, "fallback_model": fb}
            for (name, model, fb) in _SEED
        ],
    )


def downgrade() -> None:
    op.drop_table("agent_config")
