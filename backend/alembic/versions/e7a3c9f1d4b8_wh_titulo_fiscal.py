"""warehouse: wh_titulo_fiscal — ponte titulo <-> NF-e (lastro fiscal).

Revision ID: e7a3c9f1d4b8
Revises: d8b4f1c6a9e2
Create Date: 2026-07-11 15:00:00.000000

Fonte: Bitfin TituloFiscal (join DocumentoFiscalNFe p/ chave de 44).
Consumo: escopo do monitoramento SERPRO (titulo em aberto => vigia chave).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a3c9f1d4b8"
down_revision: str | None = "d8b4f1c6a9e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wh_titulo_fiscal",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("titulo_id", sa.Integer, nullable=False),
        sa.Column("nota_fiscal_eletronica_id", sa.Integer, nullable=False),
        sa.Column("chave_acesso", sa.String(44), nullable=False),
        sa.Column("valor_associado", sa.Numeric(18, 4), nullable=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("hash_origem", sa.String(64), nullable=True),
        sa.Column("ingested_by_version", sa.String(128), nullable=False),
        sa.Column("trust_level", sa.String(16), nullable=False),
        sa.Column("collected_by", UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "source_id", name="uq_wh_titulo_fiscal"),
    )
    op.create_index(
        "ix_wh_titulo_fiscal_tenant_id", "wh_titulo_fiscal", ["tenant_id"]
    )
    op.create_index(
        "ix_wh_titulo_fiscal_tenant_titulo",
        "wh_titulo_fiscal",
        ["tenant_id", "titulo_id"],
    )
    op.create_index(
        "ix_wh_titulo_fiscal_tenant_chave",
        "wh_titulo_fiscal",
        ["tenant_id", "chave_acesso"],
    )
    op.create_index(
        "ix_wh_titulo_fiscal_source_type", "wh_titulo_fiscal", ["source_type"]
    )
    op.create_index(
        "ix_wh_titulo_fiscal_source_id", "wh_titulo_fiscal", ["source_id"]
    )


def downgrade() -> None:
    op.drop_table("wh_titulo_fiscal")
