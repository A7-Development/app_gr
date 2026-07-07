"""filedrop_landing_zone

Revision ID: b2d7e4a8c1f5
Revises: d2e8a4c1f9b7
Create Date: 2026-07-06

Fase 1 da landing zone multi-tenant de arquivos (plano "Landing Zone
Multi-tenant" 2026-07-06 — Strata Collector + object storage):

1. `agent_credential` — token de maquina do Strata Collector (agente no
   servidor do cliente). Guarda so o sha256 do token; revogacao via
   `revoked_at`; politica de coleta (`watch_config` JSONB) devolvida ao
   agente no /ping.
2. `file_landing` — registry bronze (§13.2) da landing zone: 1 linha por
   arquivo recebido pelo File Gateway, com proveniencia (sha256,
   received_at, agent_credential_id, agent_version) e ponteiro pro blob
   no StorageBackend (`storage_key`). Dedup por
   (tenant_id, source_label, sha256).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b2d7e4a8c1f5"
down_revision: str | None = "d2e8a4c1f9b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_credential",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "unidade_administrativa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "cadastros_unidade_administrativa.id", ondelete="RESTRICT"
            ),
            nullable=True,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "watch_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("agent_version", sa.String(32), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_agent_credential_tenant_id", "agent_credential", ["tenant_id"]
    )
    op.create_index(
        "ix_agent_credential_unidade_administrativa_id",
        "agent_credential",
        ["unidade_administrativa_id"],
    )
    op.create_index(
        "ix_agent_credential_token_hash",
        "agent_credential",
        ["token_hash"],
        unique=True,
    )

    op.create_table(
        "file_landing",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "unidade_administrativa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "cadastros_unidade_administrativa.id", ondelete="RESTRICT"
            ),
            nullable=True,
        ),
        sa.Column("source_label", sa.String(64), nullable=False),
        sa.Column("nome_arquivo", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "agent_credential_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_credential.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent_version", sa.String(32), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "source_label",
            "sha256",
            name="uq_file_landing_tenant_source_sha",
        ),
    )
    op.create_index("ix_file_landing_tenant_id", "file_landing", ["tenant_id"])
    op.create_index(
        "ix_file_landing_unidade_administrativa_id",
        "file_landing",
        ["unidade_administrativa_id"],
    )
    op.create_index(
        "ix_file_landing_tenant_source_received",
        "file_landing",
        ["tenant_id", "source_label", "received_at"],
    )


def downgrade() -> None:
    op.drop_table("file_landing")
    op.drop_table("agent_credential")
