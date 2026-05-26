"""bitfin serasa relay: bitfin_consulta_id + endpoint TSEC seed

Suporta o relay automatico das consultas Serasa armazenadas no Bitfin
(dbo.ConsultaFinanceira) para o warehouse wh_serasa_pj_*, modelado como o
endpoint de sync `bitfin.serasa_relay`.

1. Coluna `bitfin_consulta_id` (BIGINT, nullable) em wh_serasa_pj_raw_relatorio
   + indice unico parcial (tenant_id, bitfin_consulta_id) WHERE NOT NULL.
   Serve de idempotencia (ON CONFLICT) e de watermark (MAX por tenant).
2. Seed da linha TSEC `bitfin.serasa_relay` (interval 15 min, enabled) pra cada
   tenant que ja tem `bitfin.full_sync` — espelhando tenant/source/env/ua
   (a UA precisa bater pra a credencial Bitfin resolver).

Revision ID: c7d9e1f3a5b8
Revises: a1b2c3d4e5f6
Create Date: 2026-05-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c7d9e1f3a5b8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

_TABLE = "wh_serasa_pj_raw_relatorio"
_INDEX = "uq_serasa_pj_raw_bitfin_consulta"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("bitfin_consulta_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        _INDEX,
        _TABLE,
        ["tenant_id", "bitfin_consulta_id"],
        unique=True,
        postgresql_where=sa.text("bitfin_consulta_id IS NOT NULL"),
    )
    # Seed TSEC do endpoint relay, espelhando cada linha bitfin.full_sync.
    op.execute(
        sa.text(
            "INSERT INTO tenant_source_endpoint_config "
            "(id, tenant_id, source_type, environment, "
            " unidade_administrativa_id, endpoint_name, enabled, "
            " schedule_kind, schedule_value, created_at, updated_at) "
            "SELECT gen_random_uuid(), tenant_id, source_type, environment, "
            "       unidade_administrativa_id, 'bitfin.serasa_relay', true, "
            "       'interval', '15', now(), now() "
            "FROM tenant_source_endpoint_config "
            "WHERE endpoint_name = 'bitfin.full_sync' "
            "ON CONFLICT ON CONSTRAINT uq_tenant_source_env_ua_endpoint "
            "DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM tenant_source_endpoint_config "
            "WHERE endpoint_name = 'bitfin.serasa_relay'"
        )
    )
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, "bitfin_consulta_id")
