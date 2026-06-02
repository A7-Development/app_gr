"""wh_liquidacao_recebivel: UQ inclui data_posicao + tipo_movimento

Revision ID: c3f8b1d6e4a2
Revises: a7e3c1f9d2b4
Create Date: 2026-06-02 19:30:00.000000

A UQ antiga `(tenant_id, fundo_doc, id_recebivel)` assumia "1 baixa final por
recebivel" — premissa FALSA. A QiTech emite MULTIPLOS movimentos por recebivel
em `fidc-custodia/liquidados-baixados` (ex.: LIQUIDACAO PARCIAL em datas
distintas + BAIXA final). Com a UQ antiga, todos colapsavam numa linha (upsert
sobrescrevia), e so o ultimo movimento ingerido sobrevivia — as parciais eram
perdidas e a queda de VP correspondente aparecia no drill de DC como "mutacao
silenciosa" inexplicada.

Caso canonico (DID94813 / id_recebivel 410533736, REALINVEST):
  22/05 LIQUIDACAO PARCIAL  valorPago  2.409,27
  26/05 LIQUIDACAO PARCIAL  valorPago 15.101,64   <- virava "mutacao silenciosa"
  28/05 BAIXA POR DEPOSITO CEDENTE valorPago 10.082,73   <- unica que sobrevivia

Fix: a UQ passa a incluir `data_posicao` (data do movimento, NOT NULL) e
`tipo_movimento` (seguranca contra 2 movimentos de tipos diferentes no mesmo
dia). Pareado com:
  - mapper `liquidados_baixados.py`: source_id inclui data_posicao
  - sync `custodia.py`: conflict_columns inclui data_posicao + tipo_movimento

Nao precisa dedup antes do ADD: a UQ nova e um SUPERSET de colunas da antiga,
entao toda linha ja existente (unica sob a chave antiga) continua unica sob a
nova. As parciais perdidas voltam no proximo re-map/resync do raw (imutavel).

Todas as colunas da UQ sao NOT NULL — NULLS NOT DISTINCT e irrelevante aqui.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f8b1d6e4a2"
down_revision: str | None = "a7e3c1f9d2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE wh_liquidacao_recebivel "
        "DROP CONSTRAINT uq_wh_liquidacao_recebivel"
    )
    op.execute(
        "ALTER TABLE wh_liquidacao_recebivel ADD CONSTRAINT uq_wh_liquidacao_recebivel "
        "UNIQUE (tenant_id, fundo_doc, id_recebivel, data_posicao, tipo_movimento)"
    )


def downgrade() -> None:
    # Volta a chave antiga. ATENCAO: se o resync ja gravou multiplos movimentos
    # por recebivel, este downgrade FALHA com duplicate key — e esperado
    # (a premissa antiga ja nao vale). Rode so antes do resync.
    op.execute(
        "ALTER TABLE wh_liquidacao_recebivel "
        "DROP CONSTRAINT uq_wh_liquidacao_recebivel"
    )
    op.execute(
        "ALTER TABLE wh_liquidacao_recebivel ADD CONSTRAINT uq_wh_liquidacao_recebivel "
        "UNIQUE (tenant_id, fundo_doc, id_recebivel)"
    )
