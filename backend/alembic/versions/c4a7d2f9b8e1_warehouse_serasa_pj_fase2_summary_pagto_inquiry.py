"""warehouse: serasa_pj fase 2 (restricao_summary, pagamento_bucket, inquiry_anterior)

Revision ID: c4a7d2f9b8e1
Revises: b8e3a1f2c5d9
Create Date: 2026-05-01 21:00:00.000000

Adiciona 3 tabelas silver pra cobrir blocos do payload Serasa PJ que
nao foram modelados na Fase 1 (descobertos com payload real em
2026-05-01):

1. `wh_serasa_pj_restricao_summary` — sumario agregado por categoria
   (count + balance + first/last occurrence). Vem de
   `negativeData.<categoria>.summary`. Util pra dashboards e queries de
   risco sem JOIN nas filhas individuais.

2. `wh_serasa_pj_pagamento_bucket` — buckets de pontualidade do
   `advancedCommercialPaymentHistory.paymentHistory.titlesQuantity[]`.
   Cada bucket descreve uma faixa de atraso ("PONTUAL", "ATE 30 DIAS",
   etc) com % do total e valores absolutos. RICO pra credito B2B.

3. `wh_serasa_pj_inquiry_anterior` — `facts.inquiryCompanyResponse.results[]`,
   lista de quem consultou esse CNPJ recentemente (companyName,
   companyDocumentId, occurrenceDate, daysQuantity).

Todas usam mixin Auditable (silver). FK `consulta_id` -> `wh_serasa_pj_consulta`
com ON DELETE CASCADE.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a7d2f9b8e1"
down_revision: str | None = "b8e3a1f2c5d9"
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
    # ─── wh_serasa_pj_restricao_summary ────────────────────────────────────
    op.create_table(
        "wh_serasa_pj_restricao_summary",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        # 'pefin' | 'refin' | 'protesto' | 'cheque' | 'collection'
        sa.Column("tipo", sa.String(length=16), nullable=False),
        sa.Column(
            "count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "balance", sa.Numeric(precision=20, scale=2), nullable=True
        ),
        sa.Column("first_occurrence", sa.Date(), nullable=True),
        sa.Column("last_occurrence", sa.Date(), nullable=True),
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
            name="uq_wh_serasa_pj_restricao_summary",
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_restricao_summary_tenant_id",
        "wh_serasa_pj_restricao_summary",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_restricao_summary_consulta_id",
        "wh_serasa_pj_restricao_summary",
        ["consulta_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_restricao_summary_tenant_tipo",
        "wh_serasa_pj_restricao_summary",
        ["tenant_id", "tipo"],
    )

    # ─── wh_serasa_pj_pagamento_bucket ─────────────────────────────────────
    op.create_table(
        "wh_serasa_pj_pagamento_bucket",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        # Tipo do segmento (drawee/assignor/individual). Hoje so factoring
        # vem populado, mas tabela aceita qualquer um.
        sa.Column("segment_kind", sa.String(length=16), nullable=False),
        # Nome do bucket: "PONTUAL", "ATE 30 DIAS", "DE 31 A 60 DIAS", etc.
        sa.Column("name", sa.String(length=64), nullable=False),
        # Faixa textual do bucket ("-", "1-30", "31-60", "61-90", ...).
        sa.Column("range_label", sa.String(length=32), nullable=True),
        sa.Column("range_code", sa.String(length=16), nullable=True),
        # Faixa numerica de valores cobertos pelo bucket.
        sa.Column(
            "range_value_from",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        sa.Column(
            "range_value_to",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        # Faixa de % do total que cai neste bucket (Serasa devolve range
        # `from`/`to`, ex.: "0.0% e 0.0%" -> 0.0/0.0).
        sa.Column(
            "percentage_from",
            sa.Numeric(precision=8, scale=4),
            nullable=True,
        ),
        sa.Column(
            "percentage_to",
            sa.Numeric(precision=8, scale=4),
            nullable=True,
        ),
        # String original do percentage como Serasa devolveu.
        sa.Column(
            "percentage_label", sa.String(length=64), nullable=True
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
            name="uq_wh_serasa_pj_pagamento_bucket",
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_pagamento_bucket_tenant_id",
        "wh_serasa_pj_pagamento_bucket",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_pagamento_bucket_consulta_id",
        "wh_serasa_pj_pagamento_bucket",
        ["consulta_id"],
    )

    # ─── wh_serasa_pj_inquiry_anterior ─────────────────────────────────────
    op.create_table(
        "wh_serasa_pj_inquiry_anterior",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        # CNPJ de quem consultou (so digitos).
        sa.Column(
            "company_document_id", sa.String(length=14), nullable=True
        ),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("company_alias", sa.Text(), nullable=True),
        sa.Column("occurrence_date", sa.Date(), nullable=True),
        sa.Column("days_quantity", sa.Integer(), nullable=True),
        # Bloco bruto preservado (inclui campos extras de versoes futuras).
        sa.Column(
            "detalhe", postgresql.JSONB(astext_type=sa.Text()), nullable=True
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
            name="uq_wh_serasa_pj_inquiry_anterior",
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_inquiry_anterior_tenant_id",
        "wh_serasa_pj_inquiry_anterior",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_inquiry_anterior_consulta_id",
        "wh_serasa_pj_inquiry_anterior",
        ["consulta_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_inquiry_anterior_company_document_id",
        "wh_serasa_pj_inquiry_anterior",
        ["company_document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wh_serasa_pj_inquiry_anterior_company_document_id",
        table_name="wh_serasa_pj_inquiry_anterior",
    )
    op.drop_index(
        "ix_wh_serasa_pj_inquiry_anterior_consulta_id",
        table_name="wh_serasa_pj_inquiry_anterior",
    )
    op.drop_index(
        "ix_wh_serasa_pj_inquiry_anterior_tenant_id",
        table_name="wh_serasa_pj_inquiry_anterior",
    )
    op.drop_table("wh_serasa_pj_inquiry_anterior")

    op.drop_index(
        "ix_wh_serasa_pj_pagamento_bucket_consulta_id",
        table_name="wh_serasa_pj_pagamento_bucket",
    )
    op.drop_index(
        "ix_wh_serasa_pj_pagamento_bucket_tenant_id",
        table_name="wh_serasa_pj_pagamento_bucket",
    )
    op.drop_table("wh_serasa_pj_pagamento_bucket")

    op.drop_index(
        "ix_wh_serasa_pj_restricao_summary_tenant_tipo",
        table_name="wh_serasa_pj_restricao_summary",
    )
    op.drop_index(
        "ix_wh_serasa_pj_restricao_summary_consulta_id",
        table_name="wh_serasa_pj_restricao_summary",
    )
    op.drop_index(
        "ix_wh_serasa_pj_restricao_summary_tenant_id",
        table_name="wh_serasa_pj_restricao_summary",
    )
    op.drop_table("wh_serasa_pj_restricao_summary")
