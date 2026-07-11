"""sinal_prc05_curadoria

Revision ID: a5d8e2c7f1b4
Revises: f2c7d4a9e3b1
Create Date: 2026-07-11

PRC-05 no catalogo (decisao Ricardo 2026-07-11): pagamento na agencia da
conta do cedente com sacado da MESMA cidade e AMBIGUO (cidade pequena =
agencia unica) — nao e inocencia automatica nem fraude automatica; trava a
nota como critico PENDENTE ate a curadoria humana liberar (tag OK) ou
confirmar (tag FRAUDE). Severidade propria `pendente` marca o carater
provisorio; a tag humana manda sobre qualquer sinal automatico.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a5d8e2c7f1b4"
down_revision: str | Sequence[str] | None = "f2c7d4a9e3b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sinais = sa.table(
        "deteccao_sinal",
        sa.column("codigo", sa.String),
        sa.column("familia", sa.String),
        sa.column("nome", sa.String),
        sa.column("definicao", sa.String),
        sa.column("severidade", sa.String),
        sa.column("status", sa.String),
        sa.column("feature_name", sa.String),
    )
    op.bulk_insert(
        sinais,
        [
            {
                "codigo": "PRC-05",
                "familia": "praca",
                "nome": "Agencia da conta do cedente, mesma cidade (curadoria)",
                "definicao": (
                    "Boleto liquidado na agencia onde o cedente tem conta, com "
                    "sacado da MESMA cidade — ambiguo (cidade pequena = agencia "
                    "unica da praca). Nao e inocencia nem fraude automatica: trava "
                    "a nota como critico PENDENTE ate a curadoria humana liberar "
                    "(tag OK) ou confirmar (tag FRAUDE). Humano manda sobre o "
                    "automatico."
                ),
                "severidade": "pendente",
                "status": "ativo",
                "feature_name": None,
            },
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM deteccao_sinal WHERE codigo = 'PRC-05'")
