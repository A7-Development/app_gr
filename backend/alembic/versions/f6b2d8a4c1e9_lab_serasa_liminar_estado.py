"""lab_serasa_liminar_estado -- maquina de estados da suspeita de liminar

Estado persistido por (tenant, CNPJ) da regra serasa_liminar_v1: uma vez
sob "NADA CONSTA", o CNPJ nunca sai silenciosamente da deteccao — so
transiciona (suspeita_ativa / liminar_caida / transicao_ambigua), com
toda transicao gravada em decision_log pela sentinela
(app/modules/integracoes/services/serasa_liminar_sentinela.py).

E o que fecha o ponto cego "Serasa troca o carimbo e os 32 CNPJs somem":
estado materializado + sentinela sistemica (>=3 transicoes ambiguas em
30d => alerta de mudanca de comportamento).

Backfill cronologico via scripts/serasa_liminar_estado_backfill.py
(depois do remap-all popular as colunas do silver).

Revision ID: f6b2d8a4c1e9
Revises: e3a7c1f5b9d2
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision = "f6b2d8a4c1e9"
down_revision = "e3a7c1f5b9d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lab_serasa_liminar_estado",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cnpj", sa.String(14), nullable=False),
        sa.Column("estado", sa.String(32), nullable=False),
        sa.Column(
            "primeira_evidencia_raw_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey(
                "wh_serasa_pj_raw_relatorio.id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column(
            "primeira_evidencia_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "ultima_consulta_raw_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey(
                "wh_serasa_pj_raw_relatorio.id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column(
            "ultima_consulta_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "ultima_transicao_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("regra_version", sa.String(32), nullable=False),
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
        sa.UniqueConstraint(
            "tenant_id", "cnpj", name="uq_lab_serasa_liminar_estado"
        ),
    )
    op.create_index(
        "ix_lab_serasa_liminar_estado_tenant_id",
        "lab_serasa_liminar_estado",
        ["tenant_id"],
    )
    op.create_index(
        "ix_lab_serasa_liminar_estado_tenant_estado",
        "lab_serasa_liminar_estado",
        ["tenant_id", "estado"],
    )


def downgrade() -> None:
    op.drop_table("lab_serasa_liminar_estado")
