"""integracoes: add environment column to tenant_source_config + encrypt configs

Revision ID: a7c1e5f2b3d4
Revises: 871dcc83d5b3
Create Date: 2026-04-23 12:00:00.000000

Changes:
    1. Add `environment` column (sandbox|production) to `tenant_source_config`.
    2. Replace unique constraint (tenant_id, source_type) with
       (tenant_id, source_type, environment) so a tenant can keep sandbox
       and production coexisting.
    3. Re-encrypt every row's `config` as an envelope (v1) using
       `app.shared.crypto.envelope`. Idempotent — rows that already look like
       envelopes are left alone.

Downgrade:
    - Decrypts envelopes back to plaintext (requires same APP_CONFIG_KEK).
    - Drops environment column + restores old unique constraint.
"""
import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.shared.crypto.envelope import (
    decrypt_envelope,
    encrypt_envelope,
    is_envelope,
)

# revision identifiers, used by Alembic.
revision: str = "a7c1e5f2b3d4"
down_revision: str | None = "871dcc83d5b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add environment column (default production for existing rows)
    op.add_column(
        "tenant_source_config",
        sa.Column(
            "environment",
            sa.Enum(
                "SANDBOX",
                "PRODUCTION",
                name="environment",
                native_enum=False,
                length=16,
            ),
            nullable=False,
            server_default="PRODUCTION",
        ),
    )

    # 2. Rotate unique constraint
    op.drop_constraint("uq_tenant_source", "tenant_source_config", type_="unique")
    op.create_unique_constraint(
        "uq_tenant_source_env",
        "tenant_source_config",
        ["tenant_id", "source_type", "environment"],
    )

    # 3. Re-encrypt each row's `config` in place
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, config FROM tenant_source_config")
    ).fetchall()

    for row_id, cfg in rows:
        if is_envelope(cfg):
            continue  # already encrypted
        if not isinstance(cfg, dict):
            continue  # null/malformed; skip
        enc = encrypt_envelope(cfg)
        bind.execute(
            sa.text(
                "UPDATE tenant_source_config SET config = CAST(:c AS jsonb) "
                "WHERE id = :id"
            ),
            {"c": json.dumps(enc), "id": row_id},
        )


def downgrade() -> None:
    # Decrypt envelopes back to plaintext dicts
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, config FROM tenant_source_config")
    ).fetchall()
    for row_id, cfg in rows:
        if not is_envelope(cfg):
            continue
        plain = decrypt_envelope(cfg)
        bind.execute(
            sa.text(
                "UPDATE tenant_source_config SET config = CAST(:c AS jsonb) "
                "WHERE id = :id"
            ),
            {"c": json.dumps(plain), "id": row_id},
        )

    # Restore old unique constraint + drop environment column
    op.drop_constraint(
        "uq_tenant_source_env", "tenant_source_config", type_="unique"
    )
    op.create_unique_constraint(
        "uq_tenant_source", "tenant_source_config", ["tenant_id", "source_type"]
    )
    op.drop_column("tenant_source_config", "environment")
