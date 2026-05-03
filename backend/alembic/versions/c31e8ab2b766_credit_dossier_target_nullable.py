"""credit_dossier_target_nullable

Tira a obrigatoriedade de PJ do dossier. Antes, target_cnpj e target_name
eram NOT NULL — o que amarrava o produto a fluxos de PJ. Com a nova
arquitetura "fluxo define a entidade analisada", esses campos passam a ser
populados pelo motor a partir de human_input que coleta cnpj/cpf/razao_social
ou ficam nulos para fluxos sem identidade explicita (simulacao, analise de
produto etc).

Compatibilidade: dados existentes nao mudam. Apenas remove a constraint.

Revision ID: c31e8ab2b766
Revises: a4f7e2c8b1d5
Create Date: 2026-05-02 19:58:45.017823
"""
from collections.abc import Sequence

from alembic import op


revision: str = 'c31e8ab2b766'
down_revision: str | None = 'a4f7e2c8b1d5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "credit_dossier",
        "target_cnpj",
        nullable=True,
    )
    op.alter_column(
        "credit_dossier",
        "target_name",
        nullable=True,
    )


def downgrade() -> None:
    # ATENCAO: linhas com NULL em qualquer dos campos quebram esse downgrade.
    # Em prod, antes de reverter: UPDATE credit_dossier SET target_cnpj = '',
    # target_name = '' WHERE * IS NULL. Em dev, drop+recreate da tabela e
    # mais barato.
    op.alter_column(
        "credit_dossier",
        "target_cnpj",
        nullable=False,
    )
    op.alter_column(
        "credit_dossier",
        "target_name",
        nullable=False,
    )
