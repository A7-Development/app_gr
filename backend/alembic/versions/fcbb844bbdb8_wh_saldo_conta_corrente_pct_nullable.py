"""wh_saldo_conta_corrente: percentuais nullable

Revision ID: fcbb844bbdb8
Revises: f9b08c7d4a52
Create Date: 2026-04-26 14:47:22.032955

Why: QiTech as vezes devolve lixo numerico (~1e18) em
`percentualSobreContaCorrente` quando o saldo liquido da carteira e zero
(float divide-by-near-zero do lado deles). Esses valores nao cabem em
NUMERIC(8,4) e estouram a transacao. Validado em 2026-04-26 com REALINVEST
(soma BRADESCO + CONCILIA + SOCOPA = 0,00) — pct chegou como
-6.234.570.403.704.996.000.

Decisao: o mapper agora clampa pra None quando |pct| > 9999.9999. Pra isso
funcionar, as colunas precisam aceitar NULL. None aqui significa
"desconhecido" (fonte nao computou) e e mais honesto que gravar 0.

Aplica nas duas colunas de pct (`percentual_sobre_conta_corrente` e
`percentual_sobre_total`) por simetria — mesma raiz da falha pode atingir
o segundo campo no mesmo cenario.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fcbb844bbdb8"
down_revision: str | None = "f9b08c7d4a52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "wh_saldo_conta_corrente",
        "percentual_sobre_conta_corrente",
        existing_type=sa.Numeric(8, 4),
        nullable=True,
    )
    op.alter_column(
        "wh_saldo_conta_corrente",
        "percentual_sobre_total",
        existing_type=sa.Numeric(8, 4),
        nullable=True,
    )


def downgrade() -> None:
    # Antes de reaplicar NOT NULL, qualquer linha com NULL precisa ser
    # corrigida (ex.: backfill com 0). Sem isso o ALTER falha. Como
    # downgrade nao deve corromper dado, deixamos o operador resolver
    # manualmente — esse downgrade e best-effort e so funciona se nao
    # houver linha nula. Em prod essa migration nao deve voltar.
    op.alter_column(
        "wh_saldo_conta_corrente",
        "percentual_sobre_total",
        existing_type=sa.Numeric(8, 4),
        nullable=False,
    )
    op.alter_column(
        "wh_saldo_conta_corrente",
        "percentual_sobre_conta_corrente",
        existing_type=sa.Numeric(8, 4),
        nullable=False,
    )
