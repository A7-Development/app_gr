"""endpoint_date_state: F1 do refactor de sync (state machine)

Revision ID: b4f1a8d2c903
Revises: e8a2b9c4d167
Create Date: 2026-05-19 10:00:00.000000

Cria a tabela `endpoint_date_state` — 1 row por (tenant, source, env, ua,
endpoint, data_referencia) representando o estado da sincronizacao de UM
dia de UM endpoint. Substitui o emaranhado de 4 mecanismos legados
(reconciler + watermark + refresh_complete + cap absoluto) por 1 unico
modelo data-driven.

Ver `project_qitech_sync_state_machine` memory pra contexto completo.

Estrutura:
- PK uuid id + UNIQUE em (tenant, source, env, ua, endpoint, data).
- state CHECK constraint validando o vocabulario de 7 estados.
- Index parcial em next_attempt_at WHERE state NOT IN (complete, in_flight,
  abandoned) — query do scheduler tick filtra exatamente assim, e o
  partial index reduz tamanho.

Os campos `state_machine_enabled` e `refresh_complete_window_business_days`
no `EndpointSpec` sao codigo (dataclass frozen) — nao precisam de migration.

Down_revision aponta direto pra `e8a2b9c4d167` (paralelo a migration de
identity `d7e3a9b1f4c2` que sera commitada em sessao separada). Quando
ambas convergirem em prod, criar `alembic merge` pra unificar as heads.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4f1a8d2c903"
down_revision: str | None = "e8a2b9c4d167"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "endpoint_date_state",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.Enum(
                "ERP_BITFIN",
                "ADMIN_QITECH",
                "BUREAU_SERASA_PJ",
                "BUREAU_SERASA_PF",
                name="source_type",
                native_enum=False,
                length=64,
                create_constraint=False,
            ),
            sa.ForeignKey("source_catalog.source_type"),
            nullable=False,
        ),
        sa.Column(
            "environment",
            sa.Enum(
                "PRODUCTION",
                "SANDBOX",
                name="environment",
                native_enum=False,
                length=16,
                create_constraint=False,
            ),
            server_default="PRODUCTION",
            nullable=False,
        ),
        sa.Column(
            "unidade_administrativa_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "cadastros_unidade_administrativa.id", ondelete="RESTRICT"
            ),
            nullable=True,
        ),
        sa.Column("endpoint_name", sa.String(128), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column(
            "state",
            sa.String(16),
            nullable=False,
            server_default="not_started",
        ),
        sa.Column(
            "next_attempt_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "attempts_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "last_attempt_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("last_completeness", sa.String(16), nullable=True),
        sa.Column("backoff_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_type",
            "environment",
            "unidade_administrativa_id",
            "endpoint_name",
            "data_referencia",
            name="uq_endpoint_date_state",
        ),
        sa.CheckConstraint(
            "state IN ("
            "'not_started', 'in_flight', 'complete', 'empty', "
            "'partial', 'not_published', 'abandoned'"
            ")",
            name="ck_endpoint_date_state_state",
        ),
        sa.CheckConstraint(
            "attempts_count >= 0",
            name="ck_endpoint_date_state_attempts_nonneg",
        ),
        sa.CheckConstraint(
            "backoff_seconds IS NULL OR backoff_seconds >= 0",
            name="ck_endpoint_date_state_backoff_nonneg",
        ),
        sa.CheckConstraint(
            "(state = 'abandoned' AND next_attempt_at IS NULL) "
            "OR (state != 'abandoned')",
            name="ck_endpoint_date_state_terminal_next_attempt",
        ),
    )

    # NULLS NOT DISTINCT na unique constraint pra UA NULL coexistir — segue
    # padrao das outras tables (tenant_source_config, tenant_source_endpoint_config).
    # SQLAlchemy 2.0 ainda nao suporta isso nativamente em UniqueConstraint;
    # recriamos manualmente.
    op.execute(
        "ALTER TABLE endpoint_date_state "
        "DROP CONSTRAINT uq_endpoint_date_state"
    )
    op.execute(
        "ALTER TABLE endpoint_date_state ADD CONSTRAINT uq_endpoint_date_state "
        "UNIQUE NULLS NOT DISTINCT ("
        "tenant_id, source_type, environment, unidade_administrativa_id, "
        "endpoint_name, data_referencia)"
    )

    # tenant_id index (espelhando padrao TSEC — coluna ja indexada via FK
    # mas explicito ajuda planner em scans tenant-wide).
    op.create_index(
        "ix_endpoint_date_state_tenant_id",
        "endpoint_date_state",
        ["tenant_id"],
    )
    op.create_index(
        "ix_endpoint_date_state_unidade_administrativa_id",
        "endpoint_date_state",
        ["unidade_administrativa_id"],
    )
    op.create_index(
        "ix_endpoint_date_state_endpoint_name",
        "endpoint_date_state",
        ["endpoint_name"],
    )
    op.create_index(
        "ix_endpoint_date_state_data_referencia",
        "endpoint_date_state",
        ["data_referencia"],
    )

    # Index parcial pro scheduler tick — query do worker filtra exatamente
    # WHERE state NOT IN (complete, in_flight, abandoned) AND
    # next_attempt_at <= now() ORDER BY next_attempt_at LIMIT N.
    # Partial index reduz tamanho (~5x — maioria das rows estaciona em
    # complete) e melhora cardinalidade do planner.
    op.execute(
        "CREATE INDEX ix_endpoint_date_state_dispatch "
        "ON endpoint_date_state (next_attempt_at) "
        "WHERE state NOT IN ('complete', 'in_flight', 'abandoned')"
    )

    # Lookup composto pro job nightly (INSERT ON CONFLICT) e UI.
    op.create_index(
        "ix_endpoint_date_state_endpoint_date",
        "endpoint_date_state",
        ["tenant_id", "source_type", "endpoint_name", "data_referencia"],
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_endpoint_date_state_dispatch"
    )
    op.drop_index(
        "ix_endpoint_date_state_endpoint_date",
        table_name="endpoint_date_state",
    )
    op.drop_index(
        "ix_endpoint_date_state_data_referencia",
        table_name="endpoint_date_state",
    )
    op.drop_index(
        "ix_endpoint_date_state_endpoint_name",
        table_name="endpoint_date_state",
    )
    op.drop_index(
        "ix_endpoint_date_state_unidade_administrativa_id",
        table_name="endpoint_date_state",
    )
    op.drop_index(
        "ix_endpoint_date_state_tenant_id",
        table_name="endpoint_date_state",
    )
    op.drop_table("endpoint_date_state")
