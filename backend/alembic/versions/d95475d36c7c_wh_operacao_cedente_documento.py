"""wh_operacao: adiciona cedente_documento (CNPJ/CPF) + indice

Revision ID: d95475d36c7c
Revises: a7b3c9f2e1d4
Create Date: 2026-05-22

Acompanha bump bitfin_adapter v2.0.0 -> v2.1.0 que passa a resolver o
cedente direto na cadeia Bitfin (Operacao.ContaOperacionalId ->
ContaOperacional.ClienteId -> Cliente.EntidadeId -> Entidade). Ate aqui
`wh_operacao.cedente_id` e `cedente_nome` ja existiam mas estavam NULL
pra todas as 9269 ops (ETL nao populava). O documento (CNPJ/CPF, sem
mascara) e novo — util pra drill-down, exportacao e auditoria.

Apos rodar a migration:
  1. Disparar Bitfin full_sync via /integracoes/catalogo (UI)
  2. Confirmar que wh_operacao.cedente_nome ficou populado
  3. Drill /bi/operacoes4 passa a mostrar cedente real (em vez do bug
     que trazia "Wgr ..." por todas as linhas)

Coluna nullable + index parcial: a maioria das ops vai ter documento,
mas mantemos nullable porque o ETL pode falhar lookup em casos raros e
queremos absorver isso sem rejeitar a linha inteira.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "d95475d36c7c"
down_revision = "a7b3c9f2e1d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wh_operacao",
        sa.Column("cedente_documento", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_wh_operacao_cedente_documento",
        "wh_operacao",
        ["cedente_documento"],
    )


def downgrade() -> None:
    op.drop_index("ix_wh_operacao_cedente_documento", table_name="wh_operacao")
    op.drop_column("wh_operacao", "cedente_documento")
