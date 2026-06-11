"""Drop da cadeia DRE inteira (pagina /controladoria/dre morta).

Decisao Ricardo 2026-06-12: eliminar a DRE atual por completo — pagina,
API, services, classifier e TABELAS. A apuracao de receita renasceu no
catalogo caixa-fiel (wh_receita_operacional / wh_receita_caixa /
wh_receita_acruo_dia); a DRE sera reconstruida do zero depois, sobre essa
fundacao.

Morrem: wh_dre_mensal (silver), wh_bitfin_raw_dre (bronze 3 fontes),
wh_dre_classification_rule (regras de grupo + seeds), e a dim orfa
wh_dim_dre_classificacao (era do vw_DRE legacy).

Ficam: wh_bitfin_tarifa_catalogo (vocabulario), wh_bitfin_entidade (dim
generica de cedentes), e todo o catalogo de receitas.

Revision ID: b6e2a8d4f1c9
Revises: a5d9f2c7e3b1
Create Date: 2026-06-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b6e2a8d4f1c9"
down_revision: str | Sequence[str] | None = "a5d9f2c7e3b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELAS = (
    "wh_dre_mensal",
    "wh_bitfin_raw_dre",
    "wh_dre_classification_rule",
    "wh_dim_dre_classificacao",
)


def upgrade() -> None:
    for t in _TABELAS:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")


def downgrade() -> None:
    # Sem recriacao automatica: a cadeia DRE foi descontinuada por decisao
    # de produto (sera reconstruida do zero sobre o catalogo de receitas).
    # Restauracao = re-rodar as migrations historicas de criacao + re-sync.
    raise NotImplementedError("DRE chain drop e irreversivel por migration")
