"""endpoint_scheduling

Revision ID: d5bf3669b8a0
Revises: 757324f89a78
Create Date: 2026-05-05 14:00:00.000000

Refactor estrutural — cadencia por endpoint (CLAUDE.md §13 + plano em
`C:\\Users\\RicardoPimenta\\.claude\\plans\\starry-moseying-phoenix.md`):

1. Cria tabela `tenant_source_endpoint_config`. Granularidade fina:
   1 linha por (tenant, source, env, ua, endpoint_name).
2. Adiciona coluna `decision_log.endpoint_name` (+ index) — auditoria por
   endpoint sem concatenar string em `rule_or_model`.
3. Data migration: para cada TSC existente, popula N linhas em TSEC usando
   snapshot **inline** do catalogo (regra de migration: nao importa codigo
   de adapter — migrations sao auto-contidas).
   - Quando `tsc.sync_frequency_minutes IS NOT NULL` -> override INTERVAL
     daquele valor para todos os endpoints (preserva ajuste do operador).
   - Quando NULL -> usa default do snapshot.

Esta migration **nao desliga o caminho legado**. A coluna
`tenant_source_config.sync_frequency_minutes` permanece intacta e o dispatcher
escolhe modo legado vs novo via feature flag
`INTEGRACOES_USE_ENDPOINT_SCHEDULING` (default False). Drop da coluna sera
feito num PR posterior, depois de confirmar zero rollback.

Pre-requisito operacional: rodar com SCHEDULER PARADO. Sem isso, o dispatcher
pode disparar sync entre `CREATE TABLE` e o data migration, criando linhas
orfas em `decision_log`.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5bf3669b8a0"
down_revision: str | None = "757324f89a78"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ──────────────────────────────────────────────────────────────────────────
# Snapshots inline do catalogo de endpoints. CLAUDE.md regra: migrations sao
# auto-contidas — nao importam codigo de adapter (que pode mudar entre o
# momento que a migration e escrita e o momento que ela roda em prod).
# Aceita-se a duplicacao com `<adapter>/endpoint_catalog.py`. Test de
# regressao em `tests/modules/integracoes/test_endpoint_catalog.py` garante
# que catalogo no codigo nao divirja deste snapshot sem batalha consciente.
# ──────────────────────────────────────────────────────────────────────────

# Tuplas: (endpoint_name, default_kind, default_value).
# default_value = None apenas para ON_DEMAND.

QITECH_SNAPSHOT: list[tuple[str, str, str | None]] = [
    ("market.outros_fundos", "daily_at", "07:00"),
    ("market.conta_corrente", "daily_at", "07:30"),
    ("market.tesouraria", "daily_at", "07:30"),
    ("market.outros_ativos", "daily_at", "08:00"),
    ("market.demonstrativo_caixa", "daily_at", "08:00"),
    ("market.cpr", "daily_at", "08:30"),
    ("market.mec", "daily_at", "08:30"),
    ("market.rentabilidade", "daily_at", "09:00"),
    ("market.rf", "daily_at", "08:00"),
    ("market.rf_compromissadas", "daily_at", "08:00"),
    ("bank_account.balance", "daily_at", "19:00"),
    ("bank_account.statement", "interval", "60"),
]

BITFIN_SNAPSHOT: list[tuple[str, str, str | None]] = [
    ("bitfin.full_sync", "interval", "30"),
]

CATALOG_BY_SOURCE_TYPE: dict[str, list[tuple[str, str, str | None]]] = {
    # Keys = SourceType enum NAMES (e.g. "ADMIN_QITECH"), nao VALUES
    # (e.g. "admin:qitech"). SQLAlchemy `sa.Enum(SourceType)` sem
    # `values_callable` armazena o name no DB, e a query abaixo
    # (`SELECT source_type FROM tenant_source_config`) devolve o name.
    # Mismatch silencioso: original usava values e o backfill nunca
    # rodou — TSEC ficou vazia em todo deploy. Test em
    # `tests/modules/integracoes/test_migration_d5bf3669b8a0.py` blinda.
    "ADMIN_QITECH": QITECH_SNAPSHOT,
    "ERP_BITFIN": BITFIN_SNAPSHOT,
    # Bureaus + document parsers nao tem catalogo (vazio).
}


def upgrade() -> None:
    # ── 1. Cria tabela tenant_source_endpoint_config ───────────────────────
    op.create_table(
        "tenant_source_endpoint_config",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column(
            "environment",
            sa.String(16),
            nullable=False,
            server_default="PRODUCTION",
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
        sa.Column(
            "enabled",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
        sa.Column("schedule_kind", sa.String(16), nullable=False),
        sa.Column("schedule_value", sa.String(64), nullable=True),
        sa.Column(
            "last_sync_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_sync_finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_sync_status", sa.String(16), nullable=True),
        sa.Column("last_sync_error", sa.Text, nullable=True),
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
        sa.ForeignKeyConstraint(
            ["source_type"],
            ["source_catalog.source_type"],
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_type",
            "environment",
            "unidade_administrativa_id",
            "endpoint_name",
            name="uq_tenant_source_env_ua_endpoint",
        ),
        sa.CheckConstraint(
            "("
            "  schedule_kind = 'interval' "
            "  AND schedule_value ~ '^[0-9]+$' "
            "  AND schedule_value::int BETWEEN 15 AND 1440"
            ") OR ("
            "  schedule_kind = 'daily_at' "
            "  AND schedule_value ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'"
            ") OR ("
            "  schedule_kind = 'on_demand' "
            "  AND schedule_value IS NULL"
            ")",
            name="ck_tsec_schedule_value_format",
        ),
        sa.CheckConstraint(
            "last_sync_status IS NULL OR "
            "last_sync_status IN ('ok', 'erro', 'em_progresso')",
            name="ck_tsec_last_sync_status",
        ),
    )
    op.create_index(
        "ix_tenant_source_endpoint_config_tenant_id",
        "tenant_source_endpoint_config",
        ["tenant_id"],
    )
    op.create_index(
        "ix_tenant_source_endpoint_config_unidade_administrativa_id",
        "tenant_source_endpoint_config",
        ["unidade_administrativa_id"],
    )
    op.create_index(
        "ix_tenant_source_endpoint_config_endpoint_name",
        "tenant_source_endpoint_config",
        ["endpoint_name"],
    )
    op.create_index(
        "ix_tenant_source_endpoint_config_enabled",
        "tenant_source_endpoint_config",
        ["enabled"],
    )

    # ── 2. decision_log.endpoint_name (auditoria por endpoint) ─────────────
    op.add_column(
        "decision_log",
        sa.Column("endpoint_name", sa.String(128), nullable=True),
    )
    op.create_index(
        "ix_decision_log_endpoint_name",
        "decision_log",
        ["endpoint_name"],
    )

    # ── 3. Data migration: TSC -> TSEC (linhas por endpoint) ───────────────
    # Le todas as TSC existentes e cria N linhas em TSEC para cada uma,
    # respeitando o catalogo do source. Operador que ajustou
    # `sync_frequency_minutes` ganha INTERVAL daquele valor em todos os
    # endpoints (preserva intent). Operador que deixou NULL ganha defaults
    # do snapshot — comportamento conservador.
    bind = op.get_bind()
    tsc_rows = bind.execute(
        sa.text(
            "SELECT id, tenant_id, source_type, environment, "
            "unidade_administrativa_id, enabled, sync_frequency_minutes "
            "FROM tenant_source_config"
        )
    ).fetchall()

    insert_sql = sa.text(
        "INSERT INTO tenant_source_endpoint_config "
        "(id, tenant_id, source_type, environment, unidade_administrativa_id, "
        " endpoint_name, enabled, schedule_kind, schedule_value) "
        "VALUES "
        "(gen_random_uuid(), :tenant_id, :source_type, :environment, :ua_id, "
        " :endpoint_name, :enabled, :schedule_kind, :schedule_value)"
    )

    for row in tsc_rows:
        catalog = CATALOG_BY_SOURCE_TYPE.get(row.source_type, [])
        if not catalog:
            continue  # source sem catalogo (Serasa, etc) — sem TSEC linhas

        # Se operador setou freq custom, overrida todos os endpoints com
        # INTERVAL daquele valor. Caso contrario, defaults do snapshot.
        custom_freq = row.sync_frequency_minutes

        for endpoint_name, default_kind, default_value in catalog:
            if custom_freq is not None:
                schedule_kind = "interval"
                schedule_value = str(custom_freq)
            else:
                schedule_kind = default_kind
                schedule_value = default_value

            bind.execute(
                insert_sql,
                {
                    "tenant_id": row.tenant_id,
                    "source_type": row.source_type,
                    "environment": row.environment,
                    "ua_id": row.unidade_administrativa_id,
                    "endpoint_name": endpoint_name,
                    "enabled": row.enabled,
                    "schedule_kind": schedule_kind,
                    "schedule_value": schedule_value,
                },
            )


def downgrade() -> None:
    op.drop_index(
        "ix_decision_log_endpoint_name", table_name="decision_log"
    )
    op.drop_column("decision_log", "endpoint_name")

    op.drop_index(
        "ix_tenant_source_endpoint_config_enabled",
        table_name="tenant_source_endpoint_config",
    )
    op.drop_index(
        "ix_tenant_source_endpoint_config_endpoint_name",
        table_name="tenant_source_endpoint_config",
    )
    op.drop_index(
        "ix_tenant_source_endpoint_config_unidade_administrativa_id",
        table_name="tenant_source_endpoint_config",
    )
    op.drop_index(
        "ix_tenant_source_endpoint_config_tenant_id",
        table_name="tenant_source_endpoint_config",
    )
    op.drop_table("tenant_source_endpoint_config")
