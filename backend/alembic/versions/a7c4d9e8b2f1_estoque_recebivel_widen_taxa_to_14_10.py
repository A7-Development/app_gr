"""warehouse: wh_estoque_recebivel.taxa_* widen NUMERIC(12,8) -> (14,10)

CSV da QiTech entrega taxaCessao/taxaRecebivel com 10 decimais (ex.:
0,7873244904) em 100% dos titulos do sample real (auditoria 2026-05-09
sobre carteira REALINVEST de 2026-05-05, 2499 linhas, todas truncadas
silenciosamente pelo Postgres ao inserir em coluna NUMERIC(12,8)).

Em mercado regulado (CVM/ANBIMA), perda de precisao numerica em campos
de taxa entregues pela administradora e proibitiva — agrega erro em
calculo de rentabilidade da cota ao longo do tempo.

NUMERIC(14,10) preserva 10 decimais e mantem 4 digitos a esquerda
(suficiente para qualquer taxa razoavel — taxas mensais raramente passam
de 100% a.m.). Mapper Python ja produz Decimal full-precision; so o
schema estava limitando.

Revision ID: a7c4d9e8b2f1
Revises: f9a3c2b1d8e0
Create Date: 2026-05-09 21:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c4d9e8b2f1"
down_revision: str | None = "f9a3c2b1d8e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Widen — sem perda. Postgres re-escreve a coluna mas valores existentes
    # cabem trivialmente (12,8 e subset de 14,10).
    # Para repopular com a precisao plena do CSV original, rodar depois:
    #   python -m scripts.reprocess_fidc_estoque \
    #       --tenant-id <id> --data-posicao <YYYY-MM-DD>
    op.alter_column(
        "wh_estoque_recebivel",
        "taxa_cessao",
        type_=sa.Numeric(14, 10),
        existing_type=sa.Numeric(12, 8),
        existing_nullable=False,
    )
    op.alter_column(
        "wh_estoque_recebivel",
        "taxa_recebivel",
        type_=sa.Numeric(14, 10),
        existing_type=sa.Numeric(12, 8),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Narrow — pode truncar se houver linhas com >8 decimais.
    # round() garante que ALTER nao falhe por overflow de scale.
    op.execute(
        "UPDATE wh_estoque_recebivel "
        "SET taxa_cessao = round(taxa_cessao, 8), "
        "    taxa_recebivel = round(taxa_recebivel, 8)"
    )
    op.alter_column(
        "wh_estoque_recebivel",
        "taxa_cessao",
        type_=sa.Numeric(12, 8),
        existing_type=sa.Numeric(14, 10),
        existing_nullable=False,
    )
    op.alter_column(
        "wh_estoque_recebivel",
        "taxa_recebivel",
        type_=sa.Numeric(12, 8),
        existing_type=sa.Numeric(14, 10),
        existing_nullable=False,
    )
