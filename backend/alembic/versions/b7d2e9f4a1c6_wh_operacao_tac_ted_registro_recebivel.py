"""wh_operacao: tarifas TAC + TED + registros de recebiveis

Adiciona as 3 tarifas do OperacaoResultado que faltavam na ingestao:
`TarifaPorOperacao` (TAC), `TarifaDeTed` e `TotalDosRegistrosDeRecebiveis`.

Sem elas, a soma das colunas de tarifa do wh_operacao NAO reconcilia com o
desagio total embutido no ValorPresente dos itens (que e exatamente o
valor_compra enviado a QiTech na cessao ao FIDC). Validacao 2026-06-10
(op 9881): excedente total R$ 297,00 = consultas 48 + registros bancarios 60
+ fiscais 3 + comunicados 4 + docs digitais 23 + TAC 120 + TED 30 + registros
de recebiveis 9 — as colunas existentes somavam apenas R$ 138,00.

Backfill dos valores historicos: re-sync `bitfin.full_sync` (adapter
v2.4.0 re-le todas as ops pela janela do watermark) ou script ad-hoc na VM —
ate la as linhas antigas ficam com server_default 0.

Revision ID: b7d2e9f4a1c6
Revises: a9c4e7f1b2d8
Create Date: 2026-06-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7d2e9f4a1c6"
down_revision: str | Sequence[str] | None = "d9e3a7c1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    "tarifa_por_operacao",
    "tarifa_de_ted",
    "total_dos_registros_de_recebiveis",
)


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column(
            "wh_operacao",
            sa.Column(
                name,
                sa.Numeric(18, 4),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("wh_operacao", name)
