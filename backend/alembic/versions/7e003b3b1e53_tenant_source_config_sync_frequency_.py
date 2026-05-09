"""tenant_source_config sync_frequency_minutes range check

Revision ID: 7e003b3b1e53
Revises: e6c1f3a9d72b
Create Date: 2026-05-04 17:31:52.408206

Why: ate agora `sync_frequency_minutes` aceitava qualquer inteiro (incluindo
0, negativo, ou valores absurdos como 1). O scheduler dispatcher passa a ler
essa coluna pra decidir cadencia — valor invalido viria a martelar API
externa (1 min) ou ficar inerte (0). Range definido com produto:
  - minimo 15 min  -> protege ERP/admin de carga excessiva
  - maximo 1440    -> 24h, alem disso o operador deveria deixar `null`
                      (sob demanda) em vez de cron com cadencia diaria
NULL continua valido = "sob demanda" (ex.: BUREAU_SERASA_PJ).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "7e003b3b1e53"
down_revision: str | None = "e6c1f3a9d72b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_tenant_source_config_sync_frequency_range",
        "tenant_source_config",
        "sync_frequency_minutes IS NULL "
        "OR sync_frequency_minutes BETWEEN 15 AND 1440",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_tenant_source_config_sync_frequency_range",
        "tenant_source_config",
        type_="check",
    )
