"""Grupos de receita: OPERACIONAL vs POS-OPERACIONAL no catalogo de streams.

Decisao Ricardo 2026-06-12: segregar as receitas em 2 grandes grupos nos
3 metodos de visualizacao.

- OPERACIONAL: constituida DENTRO da operacao (mesmo que reconhecida depois,
  conforme o metodo): desagio de operacao, ad valorem, tarifas de operacao
  e DESAGIO DE RECOMPRA ("recompra nao e forma de identificar — desagio,
  multa e tarifa de recompra sim": a natureza manda, recompra e canal).
- POS-OPERACIONAL: nasce depois da operacao constituida: moras (liquidacao/
  prorrogacao/cartorio/acertos), juros e multa de recompra, tarifas de
  servico, repasses de custo (incl. carta de anuencia — item 2 aprovado) e
  financeira (item 3 aprovado: sem terceiro grupo).

Classificacao e CURADORIA de catalogo (coluna nova), nao codigo.

Revision ID: e8b3c5f1a7d2
Revises: d7f2c4a9e1b3
Create Date: 2026-06-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8b3c5f1a7d2"
down_revision: str | Sequence[str] | None = "d7f2c4a9e1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OPERACIONAIS = (
    "desagio_operacao",
    "tarifa_operacao",
    "ad_valorem",
    "recompra_desagio",
)


def upgrade() -> None:
    op.add_column(
        "wh_bitfin_receita_stream",
        sa.Column(
            "grupo",
            sa.String(length=20),
            nullable=False,
            server_default="pos_operacional",
        ),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE wh_bitfin_receita_stream SET grupo = 'operacional' "
            "WHERE stream_key IN :keys"
        ).bindparams(sa.bindparam("keys", expanding=True)),
        {"keys": list(_OPERACIONAIS)},
    )


def downgrade() -> None:
    op.drop_column("wh_bitfin_receita_stream", "grupo")
