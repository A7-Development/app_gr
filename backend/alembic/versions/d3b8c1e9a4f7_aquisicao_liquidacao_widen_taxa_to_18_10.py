"""warehouse: wh_{aquisicao,liquidacao}_recebivel.taxa_aquisicao widen NUMERIC(14,10) -> (18,10)

Segundo widen do mesmo dia (2026-05-12). A migration
`c7f8a3b1d9e6_aquisicao_liquidacao_widen_taxa_to_14_10.py` (precision 14,
scale 10) nao cobre o caso real observado no payload de liquidados-baixados
do REALINVEST FIDC em 2026-04-10: cessao `idRecebivel=411959061`
(cedente=FRICOCK) com `txAquisicao=201943.1021669899` — **6 digitos antes
da virgula**, enquanto (14,10) so permite 4.

Backfill de abril/2026 chunk 08-14/04 fica bloqueado por essa 1 cessao
(rollback do batch inteiro, 770 cessoes saudaveis ficam de fora do silver
junto). Como a forense do incidente de 2026-04-13 (motivo do backfill)
depende desse chunk entrar, widen aceita-se ate (18,10).

(18,10): 8 digitos antes da virgula -> max 99999999.9999999999. Cobre
201943 com folga e protege contra anomalias maiores futuras. Custo: 4 bytes
a mais por linha do que (14,10) — irrisorio.

Pendencia separada (nao bloqueia esta migration): tratar valores > 9999 no
mapper como outliers (log warning + flag) em vez de aceitar silenciosamente
como taxa legitima. CLAUDE.md §14 (auditabilidade) pede que tomemos
decisao consciente sobre dado podre — TODO em followup pos-forense.

Revision ID: d3b8c1e9a4f7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-12 22:55:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3b8c1e9a4f7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "wh_aquisicao_recebivel",
        "taxa_aquisicao",
        type_=sa.Numeric(18, 10),
        existing_type=sa.Numeric(14, 10),
        existing_nullable=True,
    )
    op.alter_column(
        "wh_liquidacao_recebivel",
        "taxa_aquisicao",
        type_=sa.Numeric(18, 10),
        existing_type=sa.Numeric(14, 10),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Narrow — pode falhar se houver linhas com >4 digitos inteiros (caso
    # exato que motivou esta migration). Operador decide se aceita perda.
    op.alter_column(
        "wh_aquisicao_recebivel",
        "taxa_aquisicao",
        type_=sa.Numeric(14, 10),
        existing_type=sa.Numeric(18, 10),
        existing_nullable=True,
    )
    op.alter_column(
        "wh_liquidacao_recebivel",
        "taxa_aquisicao",
        type_=sa.Numeric(14, 10),
        existing_type=sa.Numeric(18, 10),
        existing_nullable=True,
    )
