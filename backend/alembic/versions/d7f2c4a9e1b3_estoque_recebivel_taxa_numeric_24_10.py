"""wh_estoque_recebivel: taxas NUMERIC(14,10) -> NUMERIC(24,10).

A QiTech ocasionalmente entrega `taxaRecebivel` absurda no CSV de
fidc-estoque (observado 14.962.902.343,3612 num titulo FRICOCK vencido,
posicoes de dez/2025; e 201.943,1021 em 09/04/2026). NUMERIC(14,10) so
acomoda ate 9.999,99... — o INSERT estourava `numeric field overflow`,
abortava o upsert da data INTEIRA (~2.900 linhas perdidas por 1 linha
podre) e deixava o qitech_report_job num limbo "SUCCESS sem completed_at"
(raw gravada, silver vazia). Bloqueava o backfill historico de 2025.

NUMERIC(24,10) = 14 digitos inteiros + 10 decimais — guarda com fidelidade
o valor que a fonte declarou (§14 proveniencia), mesmo quando e lixo de
calculo do vendor. Sanitizacao/flag de outlier e responsabilidade de quem
consome, nao da ingestao.

Revision ID: d7f2c4a9e1b3
Revises: b6e2a8d4f1c9
Create Date: 2026-06-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7f2c4a9e1b3"
down_revision: str | Sequence[str] | None = "b6e2a8d4f1c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "wh_estoque_recebivel",
        "taxa_cessao",
        type_=sa.Numeric(24, 10),
        existing_type=sa.Numeric(14, 10),
        existing_nullable=False,
    )
    op.alter_column(
        "wh_estoque_recebivel",
        "taxa_recebivel",
        type_=sa.Numeric(24, 10),
        existing_type=sa.Numeric(14, 10),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Falha se houver valor >= 10^4 ja ingerido (esperado — o downgrade
    # so e viavel apos limpar os outliers).
    op.alter_column(
        "wh_estoque_recebivel",
        "taxa_recebivel",
        type_=sa.Numeric(14, 10),
        existing_type=sa.Numeric(24, 10),
        existing_nullable=False,
    )
    op.alter_column(
        "wh_estoque_recebivel",
        "taxa_cessao",
        type_=sa.Numeric(14, 10),
        existing_type=sa.Numeric(24, 10),
        existing_nullable=False,
    )
