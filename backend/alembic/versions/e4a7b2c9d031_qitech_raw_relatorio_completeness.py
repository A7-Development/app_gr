"""warehouse: wh_qitech_raw_relatorio.completeness (Opcao A da resposta semantica)

Adiciona a coluna `completeness` em `wh_qitech_raw_relatorio` para distinguir
3 estados quando `http_status=200`:

- `complete`: payload integro, todos os subsets esperados presentes.
- `partial`: payload chegou mas falta subset esperado (ex.: market.rf veio so
  com clienteId='REALINVEST MEZ'/'REALINVEST SEN', sem o POV Sub Jr
  'REALINVEST' — caso visto em 12/05/2026 e 30/04/2026).
- `empty`: payload sem nenhum dado utilizavel (envelope vazio).

Hoje o pipeline trata 200 como sinonimo de "dado completo", o que faz a
pagina cota-sub renderizar Cota Mez/Sr como zero quando a administradora
publica um relatorio parcial pela QiTech. Com a nova coluna a aba Cobertura
ganha 3a cor (partial) e a UI consegue mostrar "publicacao parcial" em vez
de zero silencioso. Ver memoria project_qitech_response_semantics.md.

Schema:
- Coluna `completeness VARCHAR(20) NULL`. NULL = "ainda nao avaliado"
  (rows legacy ate o backfill rodar).
- Valores em codigo (sem enum DB pra evitar migration toda vez que
  adicionarmos status): 'complete' | 'partial' | 'empty'. CHECK constraint
  garante o subset.
- Index parcial em (tenant_id, unidade_administrativa_id, data_posicao)
  filtrado por completeness='partial' pra acelerar "dias com publicacao
  parcial" na aba Cobertura, sem onerar inserts comuns.

Revision ID: e4a7b2c9d031
Revises: d3b8c1e9a4f7
Create Date: 2026-05-13 19:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4a7b2c9d031"
down_revision: str | None = "d3b8c1e9a4f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wh_qitech_raw_relatorio",
        sa.Column("completeness", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_wh_qitech_raw_relatorio_completeness",
        "wh_qitech_raw_relatorio",
        "completeness IS NULL OR completeness IN ('complete', 'partial', 'empty')",
    )
    op.create_index(
        "ix_wh_qitech_raw_relatorio_partial",
        "wh_qitech_raw_relatorio",
        ["tenant_id", "unidade_administrativa_id", "data_posicao"],
        postgresql_where=sa.text("completeness = 'partial'"),
    )


def downgrade() -> None:
    op.drop_index("ix_wh_qitech_raw_relatorio_partial", table_name="wh_qitech_raw_relatorio")
    op.drop_constraint(
        "ck_wh_qitech_raw_relatorio_completeness",
        "wh_qitech_raw_relatorio",
        type_="check",
    )
    op.drop_column("wh_qitech_raw_relatorio", "completeness")
