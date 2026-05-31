"""wh_movimento_caixa: raw_id + seq_no -> replace-by-partition

Revision ID: f4a2c9d8e1b7
Revises: b3f8e1a9c7d2
Create Date: 2026-05-30 12:00:00.000000

Conserta dois bugs em `wh_movimento_caixa` (demonstrativo de caixa QiTech):

  BUG 1 (outage ativo desde 2026-05-20): o refactor "espelho fiel"
  (migration c8a3d2b1f7e9) trocou a escrita canonica pra
  `_replace_canonical_partition`, que referencia `model.__table__.c.raw_id`.
  `wh_movimento_caixa` foi EXPLICITAMENTE excluido daquela migration (tinha
  business key fragil), entao desde 2026-05-20 a etapa canonica do
  demonstrativo lanca excecao todo sync (engolida em step["errors"]) e o
  silver parou em 19/05. Raw segue saudavel.

  BUG 2 (duplicacao historica, pre-2026-05-20): no caminho antigo
  (_bulk_upsert_canonical, UQ (tenant_id, source_id) com source_id =
  sha16(item)), o `saldo` corrente (acumulado, volatil) entrava no hash ->
  hash drifta entre re-fetches -> source_id novo -> UQ nao colide ->
  acumula 1 copia por re-fetch (517 grupos inflados, ate 5x).

Correcao (decisao 2026-05-30): trazer a tabela pro padrao raw_id-partition,
exatamente o "refactor com seq_no" antecipado na exclusao original.

  1. `raw_id` FK pra wh_qitech_raw_relatorio (ON DELETE CASCADE, nullable
     pra retrocompat com linhas legacy) + indice — partition key do
     _replace_canonical_partition.
  2. `seq_no` int (posicao do item no snapshot) — desambigua lancamentos
     byte-iguais legitimos (ex.: 2 resgates identicos no mesmo dia, as 75
     dups REALINVEST que motivaram a exclusao). Nullable: linhas legacy
     ficam NULL.
  3. Nova UQ (tenant_id, raw_id, seq_no) — business key estavel da
     partition. Linhas legacy (raw_id NULL) ficam isentas (NULLs distintos
     no Postgres), sem quebrar a constraint.
  4. Drop da UQ antiga (tenant_id, source_id): `source_id` vira proveniencia
     pura (nao-unica). O `saldo` volatil deixa de afetar a idempotencia.

Cleanup das 517 dups historicas e re-sync do outage (20/05->hoje) sao
operacoes de DADO, fora desta migration (scripts dedicados).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4a2c9d8e1b7"
down_revision: str | None = "b3f8e1a9c7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "wh_movimento_caixa"
RAW = "wh_qitech_raw_relatorio"
FK_NAME = "fk_movimento_caixa_raw_id"
# Nome casa com o auto-nome do SQLAlchemy (raw_id index=True no model) ->
# model e DB ficam consistentes sob alembic autogenerate.
IX_NAME = "ix_wh_movimento_caixa_raw_id"
UQ_NEW = "uq_wh_movimento_caixa_raw_seq"
UQ_OLD = "uq_wh_movimento_caixa"


def upgrade() -> None:
    # 1. raw_id FK (nullable -- legacy rows ficam NULL).
    op.add_column(
        TABLE,
        sa.Column("raw_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        FK_NAME, TABLE, RAW, ["raw_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index(IX_NAME, TABLE, ["raw_id"])

    # 2. seq_no (posicao no snapshot; desambigua gemeos byte-iguais).
    op.add_column(TABLE, sa.Column("seq_no", sa.Integer(), nullable=True))

    # 3. Nova UQ da partition. Linhas legacy (raw_id NULL) isentas.
    op.create_unique_constraint(
        UQ_NEW, TABLE, ["tenant_id", "raw_id", "seq_no"]
    )

    # 4. source_id deixa de ser unico (vira proveniencia pura).
    op.drop_constraint(UQ_OLD, TABLE, type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(UQ_OLD, TABLE, ["tenant_id", "source_id"])
    op.drop_constraint(UQ_NEW, TABLE, type_="unique")
    op.drop_column(TABLE, "seq_no")
    op.drop_index(IX_NAME, table_name=TABLE)
    op.drop_constraint(FK_NAME, TABLE, type_="foreignkey")
    op.drop_column(TABLE, "raw_id")
