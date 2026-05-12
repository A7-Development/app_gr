"""warehouse: wh_{aquisicao,liquidacao}_recebivel.taxa_aquisicao widen NUMERIC(12,8) -> (14,10)

Mesmo bug que `a7c4d9e8b2f1_estoque_recebivel_widen_taxa_to_14_10.py` (2026-05-09)
ressurgindo nas tabelas irmas — `wh_aquisicao_recebivel` e
`wh_liquidacao_recebivel` tambem usam NUMERIC(12,8) para `taxa_aquisicao`,
mas a QiTech eventualmente entrega taxas com >4 digitos inteiros (ex.:
`txAquisicao=201943.1021669899` em 1 cessao de 2026-04-10 no payload de
liquidados-baixados). Bug provavelmente na QiTech, mas o sintoma no nosso
lado e:

    asyncpg.DataError: numeric field overflow
    A field with precision 12, scale 8 must round to an absolute value less than 10^4

Resultado pratico: 1 cessao anomala derruba o `_bulk_upsert_canonical` da
janela inteira (transacao aborta, 769 cessoes saudaveis tambem ficam de
fora do silver). Foi exatamente o que aconteceu no backfill de abril/2026
disparado em 2026-05-12 — chunk 08-14/04 falhou inteiro, segurando a
forense do incidente de 2026-04-13.

NUMERIC(14,10) preserva 10 decimais e mantem 4 digitos a esquerda — mesmo
limite que o estoque ja tem. Taxas absurdas como 201943 ainda passam,
mas isso e responsabilidade do consumer detectar como outlier e tratar
(filtro no dashboard / alert). O DB para de bloquear ingestao.

Revision ID: c7f8a3b1d9e6
Revises: b5e9d3a1f7c4
Create Date: 2026-05-12 22:15:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7f8a3b1d9e6"
down_revision: str | None = "b5e9d3a1f7c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Widen — sem perda. (12,8) e subset de (14,10).
    op.alter_column(
        "wh_aquisicao_recebivel",
        "taxa_aquisicao",
        type_=sa.Numeric(14, 10),
        existing_type=sa.Numeric(12, 8),
        existing_nullable=True,
    )
    op.alter_column(
        "wh_liquidacao_recebivel",
        "taxa_aquisicao",
        type_=sa.Numeric(14, 10),
        existing_type=sa.Numeric(12, 8),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Narrow — pode truncar se houver linhas com >8 decimais ou estourar
    # se houver linhas com >4 digitos inteiros. round() resolve scale;
    # overflow de precision e bloqueador consciente — operador decide.
    op.execute(
        "UPDATE wh_aquisicao_recebivel SET taxa_aquisicao = round(taxa_aquisicao, 8)"
    )
    op.execute(
        "UPDATE wh_liquidacao_recebivel SET taxa_aquisicao = round(taxa_aquisicao, 8)"
    )
    op.alter_column(
        "wh_aquisicao_recebivel",
        "taxa_aquisicao",
        type_=sa.Numeric(12, 8),
        existing_type=sa.Numeric(14, 10),
        existing_nullable=True,
    )
    op.alter_column(
        "wh_liquidacao_recebivel",
        "taxa_aquisicao",
        type_=sa.Numeric(12, 8),
        existing_type=sa.Numeric(14, 10),
        existing_nullable=True,
    )
