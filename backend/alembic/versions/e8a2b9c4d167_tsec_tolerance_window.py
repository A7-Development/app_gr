"""tsec_tolerance_window

Revision ID: e8a2b9c4d167
Revises: a9d3e7c2b5f1
Create Date: 2026-05-15 16:00:00.000000

Adiciona 3 colunas opcionais (NULL = "segue default do catalogo") em
`tenant_source_endpoint_config` representando a janela de tolerancia de
publicacao por endpoint:

- `expected_lag_business_days_override` — quantos dias uteis ANBIMA apos a
  data de referencia o dado e esperado. Para D-1 market reports = 1. Para
  balance end-of-day = 0.
- `tolerance_business_days_override` — limite superior do estado "ATRASADO"
  (ainda dentro da margem aceitavel). Acima disso vira "SUSPEITO". Deve ser
  >= expected.
- `give_up_business_days_override` — apos isso o reconciler para de tentar
  automaticamente (estado "FURO_DEFINITIVO"). Operador reabre manual. Deve
  ser >= tolerance.

NULL em qualquer coluna = "este tenant nao customizou esse limite, segue
o default do `EndpointSpec`". Catalogo no codigo continua sendo a fonte
da verdade — esta migration nao popula valores, so cria espaco pro
override.

Constraint CHECK garante monotonicidade quando os 3 sao preenchidos:
expected <= tolerance <= give_up. Se algum for NULL, a comparacao
contra ele e ignorada (semantica de "segue default" — combinacao mista
override+default e legitima e checada no `compute_publication_state`).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8a2b9c4d167"
down_revision: str | None = "a9d3e7c2b5f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tenant_source_endpoint_config") as batch:
        batch.add_column(
            sa.Column(
                "expected_lag_business_days_override",
                sa.Integer(),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "tolerance_business_days_override",
                sa.Integer(),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "give_up_business_days_override",
                sa.Integer(),
                nullable=True,
            )
        )

    # Monotonicidade: quando os 3 estao presentes, expected <= tolerance <= give_up.
    # NULL em qualquer um relaxa a comparacao correspondente — semantica de
    # "este lado segue default do catalogo". CHECK avalia para TRUE quando o lado
    # com NULL e ignorado (Postgres NULL == NULL e NULL, mas a logica e construida
    # com OR ... IS NULL pra forcar TRUE quando algum operand falta).
    op.execute(
        """
        ALTER TABLE tenant_source_endpoint_config
        ADD CONSTRAINT ck_tsec_tolerance_window_monotonic
        CHECK (
            (expected_lag_business_days_override IS NULL OR expected_lag_business_days_override >= 0)
            AND (
                expected_lag_business_days_override IS NULL
                OR tolerance_business_days_override IS NULL
                OR tolerance_business_days_override >= expected_lag_business_days_override
            )
            AND (
                tolerance_business_days_override IS NULL
                OR give_up_business_days_override IS NULL
                OR give_up_business_days_override >= tolerance_business_days_override
            )
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE tenant_source_endpoint_config "
        "DROP CONSTRAINT IF EXISTS ck_tsec_tolerance_window_monotonic"
    )
    with op.batch_alter_table("tenant_source_endpoint_config") as batch:
        batch.drop_column("give_up_business_days_override")
        batch.drop_column("tolerance_business_days_override")
        batch.drop_column("expected_lag_business_days_override")
