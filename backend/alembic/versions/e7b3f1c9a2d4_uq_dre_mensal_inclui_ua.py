"""wh_dre_mensal: incluir unidade_administrativa_id na unique key

BUGFIX: uq_wh_dre_mensal (e o source_id sintetico) omitiam o
`unidade_administrativa_id`. Quando o mesmo cedente+produto+descricao
operava em >1 fundo (A7 Credit + RealInvest) na mesma competencia, as
linhas colidiam na chave e o upsert descartava a do fundo 'perdedor'
(A7 subcontado em ~226k em maio/2026). Adicionar o ua_id na chave separa
os fundos. O `_source_id` no etl.py tambem passou a incluir o ua_id; apos
esta migration o silver e reconstruido (delete + sync_dre_mensal full).

Ver project_dre_bitfin na memoria.

Revision ID: e7b3f1c9a2d4
Revises: d5e9c1a3f7b2
Create Date: 2026-05-31
"""
from collections.abc import Sequence

from alembic import op

revision: str = "e7b3f1c9a2d4"
down_revision: str | None = "d5e9c1a3f7b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_COLS = [
    "tenant_id", "competencia", "grupo_dre", "subgrupo", "descricao",
    "entidade_id", "produto_id", "fonte",
]
_NEW_COLS = [
    "tenant_id", "competencia", "grupo_dre", "subgrupo", "descricao",
    "entidade_id", "produto_id", "unidade_administrativa_id", "fonte",
]


def upgrade() -> None:
    op.drop_constraint("uq_wh_dre_mensal", "wh_dre_mensal", type_="unique")
    op.create_unique_constraint("uq_wh_dre_mensal", "wh_dre_mensal", _NEW_COLS)


def downgrade() -> None:
    op.drop_constraint("uq_wh_dre_mensal", "wh_dre_mensal", type_="unique")
    op.create_unique_constraint("uq_wh_dre_mensal", "wh_dre_mensal", _OLD_COLS)
