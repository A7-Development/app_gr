"""integracoes: tabela operacional serpro_nfe_monitor (F3 — monitoramento push).

Revision ID: d8b4f1c6a9e2
Revises: b8e3f1a6c9d2
Create Date: 2026-07-11 12:00:00.000000

Re-encadeada c4f8a2d7e1b9 -> b8e3f1a6c9d2 (2a vez que sessoes paralelas
bifurcam a chain no mesmo dia): a chain do rating v2 (#562-#564) nasceu
sobre o head do F2 do SERPRO; este arquivo religa no head atual do main.

1 linha por (tenant, chave) vigiada. Escopo: duplicata a vencer (decisao
Ricardo 2026-07-11). Estado mutavel — tabela operacional, nao warehouse.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8b4f1c6a9e2"
down_revision: str | None = "b8e3f1a6c9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "serpro_nfe_monitor",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chave_acesso", sa.String(44), nullable=False),
        sa.Column("motivo", sa.String(32), nullable=False),
        sa.Column("referencia_vencimento", sa.Date, nullable=True),
        sa.Column(
            "ativo", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("solicitacao_id", sa.String(64), nullable=True),
        sa.Column(
            "solicitacao_expira_em", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "ultima_notificacao_em", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "ultima_consulta_em", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("ultima_situacao", sa.String(32), nullable=True),
        sa.Column("alertado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("encerrado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("encerrado_motivo", sa.String(32), nullable=True),
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
            "tenant_id", "chave_acesso", name="uq_serpro_nfe_monitor_tenant_chave"
        ),
    )
    op.create_index(
        "ix_serpro_nfe_monitor_tenant_id", "serpro_nfe_monitor", ["tenant_id"]
    )
    op.create_index(
        "ix_serpro_nfe_monitor_chave", "serpro_nfe_monitor", ["chave_acesso"]
    )
    op.create_index(
        "ix_serpro_nfe_monitor_ativo", "serpro_nfe_monitor", ["ativo"]
    )
    op.create_index(
        "ix_serpro_nfe_monitor_ativo_expira",
        "serpro_nfe_monitor",
        ["ativo", "solicitacao_expira_em"],
    )


def downgrade() -> None:
    op.drop_table("serpro_nfe_monitor")
