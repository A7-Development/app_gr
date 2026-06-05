"""wh_boleto_vigente: identidade pelo par (nosso_numero, numero_documento)

O banco REUSA o nosso_numero ao longo do tempo (reciclagem do sequencial apos
o boleto fechar) -- 635 nossos numeros aparecem para >1 documento. So o par
(nosso_numero, numero_documento) e estavel/unico. Troca a UQ.

Revision ID: e7f2a3c8b1d9
Revises: d6e3f1b9a2c8
Create Date: 2026-06-05

"""
from collections.abc import Sequence

from sqlalchemy import inspect as sa_inspect

from alembic import op

revision: str = "e7f2a3c8b1d9"
down_revision: str | None = "d6e3f1b9a2c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uniques(table: str) -> set[str]:
    insp = sa_inspect(op.get_bind())
    return {uc["name"] for uc in insp.get_unique_constraints(table)}


def upgrade() -> None:
    existing = _uniques("wh_boleto_vigente")
    if "uq_wh_boleto_vigente" in existing:
        op.drop_constraint(
            "uq_wh_boleto_vigente", "wh_boleto_vigente", type_="unique"
        )
    op.create_unique_constraint(
        "uq_wh_boleto_vigente",
        "wh_boleto_vigente",
        ["tenant_id", "banco_origem", "nosso_numero", "numero_documento"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_wh_boleto_vigente", "wh_boleto_vigente", type_="unique"
    )
    op.create_unique_constraint(
        "uq_wh_boleto_vigente",
        "wh_boleto_vigente",
        ["tenant_id", "banco_origem", "nosso_numero"],
    )
