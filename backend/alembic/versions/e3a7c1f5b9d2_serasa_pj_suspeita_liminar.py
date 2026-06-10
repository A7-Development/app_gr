"""wh_serasa_pj_consulta: negative_summary_message + suspeita_liminar

Regra serasa_liminar_v1 (descoberta 2026-06-10): quando o consultado tem
liminar judicial escondendo apontamentos negativos, a Serasa devolve
`negativeSummary: {"message": "NADA CONSTA"}` EXPLICITO no payload
RELATORIO_AVANCADO_PJ_ANALITICO — empresa genuinamente limpa vem SEM a
mensagem. Validado contra prod: 100% de correspondencia com a flag
`Liminar` do Bitfin (56/56 consultas, 32/32 CNPJs em 2.793 payloads).

- `negative_summary_message`: valor cru do payload (proveniencia/fator).
- `suspeita_liminar`: conclusao derivada pelo Strata (regra versionada em
  app/modules/integracoes/adapters/bureau/serasa_pj/liminar.py).
- Partial index para "quais CNPJs da carteira estao sob suspeita".

Populacao do historico via re-map (scripts/serasa_pj_remap_all.py) — raw
e imutavel, mapper e idempotente; nenhuma consulta paga nova.

Revision ID: e3a7c1f5b9d2
Revises: b7e2d9f4a1c6
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "e3a7c1f5b9d2"
down_revision = "b7e2d9f4a1c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("negative_summary_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column(
            "suspeita_liminar",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_consulta_tenant_suspeita_liminar",
        "wh_serasa_pj_consulta",
        ["tenant_id", "cnpj"],
        postgresql_where=sa.text("suspeita_liminar = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wh_serasa_pj_consulta_tenant_suspeita_liminar",
        table_name="wh_serasa_pj_consulta",
    )
    op.drop_column("wh_serasa_pj_consulta", "suspeita_liminar")
    op.drop_column("wh_serasa_pj_consulta", "negative_summary_message")
