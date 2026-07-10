"""warehouse: bronze wh_serpro_raw_nfe (snapshots da API SERPRO Consulta NF-e).

Revision ID: a9d1c7e4f2b8
Revises: f2a7d4c1e8b5
Create Date: 2026-07-10 18:00:00.000000

Grao: (tenant, chave, payload_sha256) — 1 linha por snapshot DISTINTO do
estado da nota. Reconsulta sem mudanca nao duplica (dedup por sha).

Encadeada apos o seed f2a7d4c1e8b5 de proposito: as duas so podem ser
aplicadas em prod DEPOIS do deploy do codigo que conhece DATA_SERPRO_NFE
(licao da 4a enum orfa, 2026-07-10 — dev DB = prod DB).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9d1c7e4f2b8"
down_revision: str | None = "f2a7d4c1e8b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wh_serpro_raw_nfe",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chave_acesso", sa.String(44), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("cstat", sa.Integer, nullable=True),
        sa.Column("qtd_eventos", sa.Integer, nullable=False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("request_tag", sa.String(32), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("fetched_by_version", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "chave_acesso",
            "payload_sha256",
            name="uq_wh_serpro_raw_nfe_dedup",
        ),
    )
    op.create_index(
        "ix_wh_serpro_raw_nfe_tenant_id", "wh_serpro_raw_nfe", ["tenant_id"]
    )
    op.create_index(
        "ix_wh_serpro_raw_nfe_tenant_chave",
        "wh_serpro_raw_nfe",
        ["tenant_id", "chave_acesso"],
    )


def downgrade() -> None:
    op.drop_table("wh_serpro_raw_nfe")
