"""warehouse: serasa_pj F.1 + F.2 (header expansao + predecessor + inquiry mensal)

Revision ID: d8f3b1a4c5e7
Revises: c4a7d2f9b8e1
Create Date: 2026-05-01 22:30:00.000000

F.1 — Expande `wh_serasa_pj_consulta` com 16 colunas que estavam sendo
descartadas no mapper anterior:

    Cadastrais (10):
        legal_nature_code, partnership_description, number_employees,
        export_sales, import_purchases, nire_number, state_registration,
        company_register, company_register_date, serasa_active_code

    Status detalhado (3):
        status_code (numerico raw "2"), status_registration_text
        ("SITUACAO DO CNPJ EM DD/MM/YYYY: ATIVA"), company_url

    Sumario de bloco `facts` (6):
        has_falencias + count_falencias + valor_falencias
        has_acoes_judiciais + count_acoes_judiciais + valor_acoes_judiciais

    Telefone (2 cols):
        phone_area_code, phone_number

F.2 — 2 tabelas novas:

    `wh_serasa_pj_predecessor` — sucessoes empresariais
    `wh_serasa_pj_inquiry_mensal` — agregado mensal de quem consultou
        (de `facts.inquiryCompanyResponse.quantity.historical[]`)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f3b1a4c5e7"
down_revision: str | None = "c4a7d2f9b8e1"
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
    # ─── F.1: ALTER wh_serasa_pj_consulta ──────────────────────────────────
    # Cadastrais.
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("legal_nature_code", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column(
            "partnership_description", sa.String(length=128), nullable=True
        ),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("number_employees", sa.Integer(), nullable=True),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column(
            "export_sales", sa.Numeric(precision=20, scale=2), nullable=True
        ),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column(
            "import_purchases",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("nire_number", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("state_registration", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("company_register", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("company_register_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("serasa_active_code", sa.String(length=16), nullable=True),
    )

    # Status detalhado.
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("status_code", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("status_registration_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("company_url", sa.Text(), nullable=True),
    )

    # Sumarios facts.bankrupts + facts.judgementFilings.
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column(
            "has_falencias",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column(
            "count_falencias",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column(
            "valor_falencias",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column(
            "has_acoes_judiciais",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column(
            "count_acoes_judiciais",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column(
            "valor_acoes_judiciais",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
    )

    # Telefone (separado em area_code + number pra queries por DDD).
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("phone_area_code", sa.String(length=4), nullable=True),
    )
    op.add_column(
        "wh_serasa_pj_consulta",
        sa.Column("phone_number", sa.String(length=20), nullable=True),
    )

    # Indexes pra queries de risco/dashboards.
    op.create_index(
        "ix_wh_serasa_pj_consulta_tenant_has_falencias",
        "wh_serasa_pj_consulta",
        ["tenant_id", "cnpj"],
        postgresql_where=sa.text("has_falencias = true"),
    )
    op.create_index(
        "ix_wh_serasa_pj_consulta_tenant_has_acoes",
        "wh_serasa_pj_consulta",
        ["tenant_id", "cnpj"],
        postgresql_where=sa.text("has_acoes_judiciais = true"),
    )

    # ─── F.2: wh_serasa_pj_predecessor ─────────────────────────────────────
    op.create_table(
        "wh_serasa_pj_predecessor",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        # Nome da empresa predecessora (sucedida pela target).
        sa.Column("predecessor_name", sa.Text(), nullable=False),
        # Data da sucessao registrada.
        sa.Column("predecessor_date", sa.Date(), nullable=True),
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
            name="uq_wh_serasa_pj_predecessor",
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_predecessor_tenant_id",
        "wh_serasa_pj_predecessor",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_predecessor_consulta_id",
        "wh_serasa_pj_predecessor",
        ["consulta_id"],
    )

    # ─── F.2: wh_serasa_pj_inquiry_mensal ──────────────────────────────────
    # Agregado mensal de consultas (13 meses tipico) — base pra grafico de
    # tendencia de "credit shopping" da empresa-alvo.
    op.create_table(
        "wh_serasa_pj_inquiry_mensal",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        # Mes de referencia: "YYYY-MM" (ex.: "2026-04").
        sa.Column("inquiry_year_month", sa.String(length=7), nullable=False),
        sa.Column(
            "occurrences",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
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
            name="uq_wh_serasa_pj_inquiry_mensal",
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_inquiry_mensal_tenant_id",
        "wh_serasa_pj_inquiry_mensal",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_inquiry_mensal_consulta_id",
        "wh_serasa_pj_inquiry_mensal",
        ["consulta_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wh_serasa_pj_inquiry_mensal_consulta_id",
        table_name="wh_serasa_pj_inquiry_mensal",
    )
    op.drop_index(
        "ix_wh_serasa_pj_inquiry_mensal_tenant_id",
        table_name="wh_serasa_pj_inquiry_mensal",
    )
    op.drop_table("wh_serasa_pj_inquiry_mensal")

    op.drop_index(
        "ix_wh_serasa_pj_predecessor_consulta_id",
        table_name="wh_serasa_pj_predecessor",
    )
    op.drop_index(
        "ix_wh_serasa_pj_predecessor_tenant_id",
        table_name="wh_serasa_pj_predecessor",
    )
    op.drop_table("wh_serasa_pj_predecessor")

    op.drop_index(
        "ix_wh_serasa_pj_consulta_tenant_has_acoes",
        table_name="wh_serasa_pj_consulta",
    )
    op.drop_index(
        "ix_wh_serasa_pj_consulta_tenant_has_falencias",
        table_name="wh_serasa_pj_consulta",
    )

    for col in (
        "phone_number",
        "phone_area_code",
        "valor_acoes_judiciais",
        "count_acoes_judiciais",
        "has_acoes_judiciais",
        "valor_falencias",
        "count_falencias",
        "has_falencias",
        "company_url",
        "status_registration_text",
        "status_code",
        "serasa_active_code",
        "company_register_date",
        "company_register",
        "state_registration",
        "nire_number",
        "import_purchases",
        "export_sales",
        "number_employees",
        "partnership_description",
        "legal_nature_code",
    ):
        op.drop_column("wh_serasa_pj_consulta", col)
