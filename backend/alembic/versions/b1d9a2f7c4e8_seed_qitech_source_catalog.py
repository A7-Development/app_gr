"""integracoes: seed source_catalog para admin:qitech.

Revision ID: b1d9a2f7c4e8
Revises: a7c1e5f2b3d4
Create Date: 2026-04-24 18:00:00.000000

Insere linha de catalogo para o adapter QiTech (admin). Nao altera schema.
O valor de enum ADMIN_QITECH ja existia desde o schema inicial — so fica
registrada a metadata do catalogo para a UI preencher o card do tenant.

Idempotente: ON CONFLICT DO NOTHING na source_type (PK).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1d9a2f7c4e8"
down_revision: str | None = "a7c1e5f2b3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


QITECH_ROW = {
    "source_type": "ADMIN_QITECH",
    "label": "QiTech (Singulare)",
    "category": "admin",
    "owner_org": "QiTech Tecnologia Financeira",
    "rate_limit_per_minute": None,  # a ser confirmado no inventario
    "unit_cost_brl": None,
    "description": (
        "Administradora/custodiante de FIDC. Portal legado em "
        "api-portal.singulare.com.br usa bearer token por POST "
        "/v2/painel/token/api."
    ),
}


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO source_catalog (
                source_type, label, category, owner_org,
                rate_limit_per_minute, unit_cost_brl, description,
                created_at, updated_at
            )
            VALUES (
                :source_type, :label, :category, :owner_org,
                :rate_limit_per_minute, :unit_cost_brl, :description,
                now(), now()
            )
            ON CONFLICT (source_type) DO NOTHING
            """
        ),
        QITECH_ROW,
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM source_catalog WHERE source_type = 'ADMIN_QITECH'")
    )
