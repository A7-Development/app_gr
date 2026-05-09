"""warehouse: serasa_pj F.3 (header tax/branch + business_ref + evolucao + atraso + comparative)

Revision ID: f9c2a6e8b3d1
Revises: d8f3b1a4c5e7
Create Date: 2026-05-01 23:30:00.000000

F.3.1 — Expande `wh_serasa_pj_consulta` com 2 campos descobertos no
payload VALOREN:
    tax_option ("LUCRO REAL" / "SIMPLES NACIONAL" / "LUCRO PRESUMIDO")
    branch_offices (string com qty/codigo de filiais)

F.3.2 — 4 tabelas silver pra capturar blocos de
`advancedCommercialPaymentHistory` que viraram visiveis com payload
real de empresa grande:

1. `wh_serasa_pj_business_reference`
   `advancedCommercialPaymentHistory.businessReferences.businessReferencesList[]`
   + paths em segmentData.{drawee,assignor}.businessReferences.
   Capacidade de compra: ULTIMA COMPRA, valor potencial em faixa.

2. `wh_serasa_pj_pagamento_evolucao_mensal`
   `advancedCommercialPaymentHistory.evolutionCommitmentsSuppliers.evolutionCommitmentsSuppliersList[]`
   + paths em segmentData.{drawee,assignor}.evolutionCommitmentsSuppliers.
   Serie temporal mensal de compromissos a vencer + em atraso.

3. `wh_serasa_pj_atraso_medio_mensal`
   `advancedCommercialPaymentHistory.segmentData.{drawee,assignor}.
    paymentHistory.averageDelayPeriod.periodList[]`.
   Atraso medio em dias por mes (com summary global).

4. `wh_serasa_pj_payment_comparative`
   `advancedCommercialPaymentHistory.segmentData.drawee.
    paymentHistoryComparativeAnalysis.paymentHistoryComparativeAnalysisList[]`.
   Comparativo mensal: empresa vs mercado vs segmento.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9c2a6e8b3d1"
down_revision: str | None = "d8f3b1a4c5e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SOURCE_TYPE_VALUES = (
    "ERP_BITFIN",
    "ADMIN_QITECH",
    "BUREAU_SERASA_PJ",
    "BUREAU_SERASA_PF",
    "BUREAU_SCR_BACEN",
    "DOCUMENT_NFE",
    "SELF_DECLARED",
    "PEER_DECLARED",
    "INTERNAL_NOTE",
    "DERIVED",
)
_TRUST_LEVEL_VALUES = ("HIGH", "MEDIUM", "LOW")


def _auditable_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "source_type",
            sa.Enum(
                *_SOURCE_TYPE_VALUES,
                name="source_type",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column(
            "source_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("hash_origem", sa.String(length=64), nullable=True),
        sa.Column(
            "ingested_by_version", sa.String(length=128), nullable=False
        ),
        sa.Column(
            "trust_level",
            sa.Enum(
                *_TRUST_LEVEL_VALUES,
                name="trust_level",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("collected_by", sa.UUID(), nullable=True),
    ]


def upgrade() -> None:
    # ─── F.3.1: ALTER wh_serasa_pj_consulta ────────────────────────────────
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("tax_option", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("branch_offices", sa.String(length=64), nullable=True),
    )

    # ─── F.3.2.A: wh_serasa_pj_business_reference ──────────────────────────
    op.create_table(
        "wh_serasa_pj_business_reference",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        sa.Column("segment_kind", sa.String(length=16), nullable=False),
        # "ULTIMA COMPRA" e variantes futuras.
        sa.Column(
            "business_description", sa.String(length=64), nullable=True
        ),
        sa.Column("reference_year", sa.String(length=4), nullable=True),
        sa.Column("reference_month", sa.String(length=2), nullable=True),
        # Faixa de valor potencial total.
        sa.Column(
            "potential_value_range_code",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column(
            "potential_value_range_description",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "potential_value_from",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        sa.Column(
            "potential_value_to",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        # Faixa intermediaria (mid-range).
        sa.Column(
            "potential_midrange_code", sa.String(length=16), nullable=True
        ),
        sa.Column(
            "potential_midrange_description",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "potential_midrange_value_from",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        sa.Column(
            "potential_midrange_value_to",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["consulta_id"],
            ["wh_serasa_pj_consulta.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_business_reference",
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_business_reference_tenant_id",
        "wh_serasa_pj_business_reference",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_business_reference_consulta_id",
        "wh_serasa_pj_business_reference",
        ["consulta_id"],
    )

    # ─── F.3.2.B: wh_serasa_pj_pagamento_evolucao_mensal ───────────────────
    op.create_table(
        "wh_serasa_pj_pagamento_evolucao_mensal",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        sa.Column("segment_kind", sa.String(length=16), nullable=False),
        # Mes/ano da observacao (ex.: year=26, month=4 -> ABR/2026).
        sa.Column("year_commitment", sa.String(length=4), nullable=True),
        sa.Column("month_commitment", sa.String(length=2), nullable=True),
        sa.Column(
            "month_description", sa.String(length=8), nullable=True
        ),
        # Codigo de segmento (e.g., "000").
        sa.Column(
            "segment_information", sa.String(length=16), nullable=True
        ),
        # Faixa de TOTAL do mes (compromisso + atraso).
        sa.Column(
            "total_month_range_code",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column(
            "total_month_range_description",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "total_monthly_range_value_from",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        sa.Column(
            "total_monthly_range_value_to",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        # Valores em faixa: "compromissos a vencer" e "compromissos
        # vencidos" do mes (em vez de numero exato — Serasa anonimiza).
        sa.Column(
            "value_commitments_due_from",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        sa.Column(
            "value_commitments_due_to",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        sa.Column(
            "value_overdue_commitments_from",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        sa.Column(
            "value_overdue_commitments_to",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        # Codigos/descricoes de faixa pra "a vencer" e "vencido".
        sa.Column(
            "track_code_to_expire", sa.String(length=16), nullable=True
        ),
        sa.Column(
            "track_description_to_expire",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "expired_track_code", sa.String(length=16), nullable=True
        ),
        sa.Column(
            "expired_track_description",
            sa.String(length=64),
            nullable=True,
        ),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["consulta_id"],
            ["wh_serasa_pj_consulta.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_pagamento_evolucao_mensal",
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_pagamento_evolucao_mensal_tenant_id",
        "wh_serasa_pj_pagamento_evolucao_mensal",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_pagamento_evolucao_mensal_consulta_id",
        "wh_serasa_pj_pagamento_evolucao_mensal",
        ["consulta_id"],
    )

    # ─── F.3.2.C: wh_serasa_pj_atraso_medio_mensal ─────────────────────────
    op.create_table(
        "wh_serasa_pj_atraso_medio_mensal",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        sa.Column("segment_kind", sa.String(length=16), nullable=False),
        # "ABR/25", "MAI/25", etc. (formato Serasa).
        sa.Column("month_label", sa.String(length=10), nullable=False),
        # Faixa de dias de atraso medio.
        sa.Column(
            "average_delay_days_from", sa.Integer(), nullable=True
        ),
        sa.Column(
            "average_delay_days_to", sa.Integer(), nullable=True
        ),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["consulta_id"],
            ["wh_serasa_pj_consulta.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_atraso_medio_mensal",
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_atraso_medio_mensal_tenant_id",
        "wh_serasa_pj_atraso_medio_mensal",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_atraso_medio_mensal_consulta_id",
        "wh_serasa_pj_atraso_medio_mensal",
        ["consulta_id"],
    )

    # ─── F.3.2.D: wh_serasa_pj_payment_comparative ─────────────────────────
    op.create_table(
        "wh_serasa_pj_payment_comparative",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        sa.Column("segment_kind", sa.String(length=16), nullable=False),
        sa.Column("month_label", sa.String(length=10), nullable=False),
        # Comparativo "market" (todos os segmentos) vs "segment" (so do
        # segmento da empresa). Cada um tem spot e installment.
        sa.Column(
            "market_origin_code", sa.String(length=8), nullable=True
        ),
        sa.Column(
            "market_spot_payment_code",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column(
            "market_spot_payment_description",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "market_installment_payment_code",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column(
            "market_installment_payment_description",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "segment_origin_code", sa.String(length=8), nullable=True
        ),
        sa.Column(
            "segment_spot_payment_code",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column(
            "segment_spot_payment_description",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "segment_installment_payment_code",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column(
            "segment_installment_payment_description",
            sa.String(length=64),
            nullable=True,
        ),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["consulta_id"],
            ["wh_serasa_pj_consulta.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_payment_comparative",
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_payment_comparative_tenant_id",
        "wh_serasa_pj_payment_comparative",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_payment_comparative_consulta_id",
        "wh_serasa_pj_payment_comparative",
        ["consulta_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wh_serasa_pj_payment_comparative_consulta_id",
        table_name="wh_serasa_pj_payment_comparative",
    )
    op.drop_index(
        "ix_wh_serasa_pj_payment_comparative_tenant_id",
        table_name="wh_serasa_pj_payment_comparative",
    )
    op.drop_table("wh_serasa_pj_payment_comparative")

    op.drop_index(
        "ix_wh_serasa_pj_atraso_medio_mensal_consulta_id",
        table_name="wh_serasa_pj_atraso_medio_mensal",
    )
    op.drop_index(
        "ix_wh_serasa_pj_atraso_medio_mensal_tenant_id",
        table_name="wh_serasa_pj_atraso_medio_mensal",
    )
    op.drop_table("wh_serasa_pj_atraso_medio_mensal")

    op.drop_index(
        "ix_wh_serasa_pj_pagamento_evolucao_mensal_consulta_id",
        table_name="wh_serasa_pj_pagamento_evolucao_mensal",
    )
    op.drop_index(
        "ix_wh_serasa_pj_pagamento_evolucao_mensal_tenant_id",
        table_name="wh_serasa_pj_pagamento_evolucao_mensal",
    )
    op.drop_table("wh_serasa_pj_pagamento_evolucao_mensal")

    op.drop_index(
        "ix_wh_serasa_pj_business_reference_consulta_id",
        table_name="wh_serasa_pj_business_reference",
    )
    op.drop_index(
        "ix_wh_serasa_pj_business_reference_tenant_id",
        table_name="wh_serasa_pj_business_reference",
    )
    op.drop_table("wh_serasa_pj_business_reference")

    op.drop_column("wh_serasa_pj_consulta", "branch_offices")
    op.drop_column("wh_serasa_pj_consulta", "tax_option")
