"""ref_bacen_segmento_oficial

Revision ID: b3d9e1f4a7c2
Revises: a2c9f4e7b6d8
Create Date: 2026-07-09

Segmento OFICIAL do Bacen (decisao Ricardo 2026-07-09: sem inferencia na
classificacao — usar a oficial; inferir so "banco digital"). Fonte: Relacao
de Instituicoes em Funcionamento (Instituicoes_em_funcionamento/Sedes*).
Casa por ISPB=CNPJ. Adiciona:
  - segmento_oficial: rotulo oficial cru (ex.: "Banco Multiplo", "IP")
  - is_banco_digital: banco sem rede fisica (<=1 agencia) — unica inferencia
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3d9e1f4a7c2"
down_revision: str | Sequence[str] | None = "a2c9f4e7b6d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ref_bacen_instituicao",
        sa.Column("segmento_oficial", sa.String(80), nullable=True),
    )
    op.add_column(
        "ref_bacen_instituicao",
        sa.Column("is_banco_digital", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ref_bacen_instituicao", "is_banco_digital")
    op.drop_column("ref_bacen_instituicao", "segmento_oficial")
