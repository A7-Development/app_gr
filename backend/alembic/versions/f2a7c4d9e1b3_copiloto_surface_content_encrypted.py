"""Copiloto (Strata AI): ai_conversation.surface + ai_message.content_encrypted

Revision ID: f2a7c4d9e1b3
Revises: b6d2f8a1c3e9
Create Date: 2026-07-23

Spec: specs/active/copiloto-mcp.md (v3), Fase 1a.

1. `ai_conversation.surface` — which chat UI owns the conversation
   ("aipanel" = drawer do BI, "copiloto" = pagina Strata AI). Os rails
   filtram por isso; historicos nunca se misturam (spec §6.5).
2. `ai_message.content_encrypted` — blocos estruturados do turno
   (tool_use/tool_result/text) em envelope Fernet (JSONB), para que o
   turno seguinte re-alimente os resultados de tools ao modelo. NULL em
   turnos so-texto.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "f2a7c4d9e1b3"
down_revision = "b6d2f8a1c3e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_conversation",
        sa.Column(
            "surface",
            sa.String(length=32),
            nullable=False,
            server_default="aipanel",
        ),
    )
    op.add_column(
        "ai_message",
        sa.Column(
            "content_encrypted",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_message", "content_encrypted")
    op.drop_column("ai_conversation", "surface")
