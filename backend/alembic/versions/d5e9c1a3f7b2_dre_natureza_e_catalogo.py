"""DRE Bitfin: catalogo de tarifas + de-para de natureza + colunas no silver

Passo 1 do redesign da Receita do DRE (Caminho A, silver canonico).

Cria:
- wh_bitfin_tarifa_catalogo  -- espelho do OrganizacaoTarifa (dim, por tenant)
- wh_bitfin_dre_natureza_rule -- de-para (fonte, categoria, descricao) -> natureza
- wh_dre_mensal.fonte_integracao -- qual integracao alimentou a linha ('bitfin')
- wh_dre_mensal.natureza         -- natureza da receita (DESAGIO/TARIFA/...)

Seed: 63 regras globais de natureza (tenant_id=NULL), ancoradas no catalogo
NATIVO do Bitfin (OrganizacaoTarifa.Tipo): Tipo 1 -> TARIFA (42 itens),
Tipo 2 -> de-para explicito (19), + 2 itens fora-de-catalogo (Credito
Estruturado). Ad Valorem e Imposto registrados mesmo sem uso na A7 (outras
factorings usam). Ver project_dre_bitfin na memoria.

Backfill: linhas existentes de wh_dre_mensal recebem fonte_integracao='bitfin'.

Revision ID: d5e9c1a3f7b2
Revises: f4a2c9d8e1b7
Create Date: 2026-05-31
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5e9c1a3f7b2"
down_revision: str | None = "f4a2c9d8e1b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tipo 1 (tarifa fixa) -> natureza TARIFA. (categoria, descricao).
_TIPO1_TARIFA: list[tuple[str, str]] = [
    # Conta Gráfica
    ("Conta Gráfica", "Despesas com Carta de Anuência"),
    ("Conta Gráfica", "Despesas com Carta de Circularização"),
    ("Conta Gráfica", "Manutenção de Títulos Vencidos"),
    ("Conta Gráfica", "Tarifa de Abatimento"),
    ("Conta Gráfica", "Tarifa de Alteração de Dados"),
    ("Conta Gráfica", "Tarifa de Alteração de Número de Título"),
    ("Conta Gráfica", "Tarifa de Baixa de Título"),
    ("Conta Gráfica", "Tarifa de Baixa por Decurso de Prazo"),
    ("Conta Gráfica", "Tarifa de Baixa por Protesto"),
    ("Conta Gráfica", "Tarifa de Cancelamento de Abatimento"),
    ("Conta Gráfica", "Tarifa de Cancelamento de Negativação"),
    ("Conta Gráfica", "Tarifa de Consulta Financeira"),
    ("Conta Gráfica", "Tarifa de Consulta Fiscal"),
    ("Conta Gráfica", "Tarifa de Liquidação"),
    ("Conta Gráfica", "Tarifa de Liquidação em Cartório"),
    ("Conta Gráfica", "Tarifa de Não Protesto"),
    ("Conta Gráfica", "Tarifa de Negativação"),
    ("Conta Gráfica", "Tarifa de PIX"),
    ("Conta Gráfica", "Tarifa de Primeira Devolução de Cheque"),
    ("Conta Gráfica", "Tarifa de Prorrogação de Título"),
    ("Conta Gráfica", "Tarifa de Protesto"),
    ("Conta Gráfica", "Tarifa de Reapresentação de Cheque"),
    ("Conta Gráfica", "Tarifa de Registro de Recebível"),
    ("Conta Gráfica", "Tarifa de Renovação Cadastral"),
    ("Conta Gráfica", "Tarifa de Segunda Devolução de Cheque"),
    ("Conta Gráfica", "Tarifa de Sustação de Protesto"),
    ("Conta Gráfica", "Tarifa de TED"),
    # Operação
    ("Operação", "Aditivo Digital"),
    ("Operação", "Comunicados de Cessão"),
    ("Operação", "Consultas Financeiras - PF"),
    ("Operação", "Consultas Financeiras - PJ"),
    ("Operação", "Consultas Fiscais"),
    ("Operação", "Duplicata Digital"),
    ("Operação", "Por Operação"),
    ("Operação", "Rebate"),
    ("Operação", "Registros Bancários"),
    ("Operação", "Registros Bancários - Pré-Impresso"),
    ("Operação", "Registros de Recebíveis"),
    ("Operação", "TED"),
    # Recompra
    ("Recompra", "Baixa"),
    ("Recompra", "Cartas de Anuências"),
    ("Recompra", "Despesas com Cartório"),
]

# Tipo 2 (encargo variavel) + itens fora-de-catalogo -> natureza explicita.
# (categoria, descricao, natureza).
_NATUREZA_EXPLICITA: list[tuple[str, str, str]] = [
    # Desagio
    ("Operação", "Deságio", "DESAGIO"),
    ("Recompra", "Deságio", "DESAGIO"),
    ("Crédito Estruturado", "Deságio", "DESAGIO"),  # fora-de-catalogo
    # Ad Valorem / Imposto (registrados; A7 sem uso, outras factorings usam)
    ("Operação", "Ad Valorem", "AD_VALOREM"),
    ("Operação", "Imposto", "IMPOSTO"),
    # Multa
    ("Título", "Multa por Atraso", "MULTA"),
    ("Recompra", "Multa", "MULTA"),
    ("Conta Gráfica", "Multa de Prorrogação de Título", "MULTA"),
    # Juros
    ("Recompra", "Juros", "JUROS"),
    ("Título", "Juros de Mora Diária", "JUROS"),
    ("Conta Gráfica", "Juros de Prorrogação de Título", "JUROS"),
    ("Conta Gráfica", "Juros por Pagamento em Cartório", "JUROS"),
    ("Conta Gráfica", "Juros Diário", "JUROS"),
    ("Conta Gráfica", "Juros Referente à Primeira Devolução de Cheque", "JUROS"),
    # Tarifa (Tipo 2 que sao servico/reembolso) + fora-de-catalogo
    ("Recompra", "Bonificação", "TARIFA"),
    ("Conta Gráfica", "Custas de Cartório", "TARIFA"),
    ("Conta Gráfica", "Despesas com Comunicados de Cessão", "TARIFA"),
    ("Conta Gráfica", "Despesas com Documentos Digitais", "TARIFA"),
    ("Conta Gráfica", "Despesas com Operação de Cobrança", "TARIFA"),
    ("Conta Gráfica", "Despesas com Operação de Custódia", "TARIFA"),
    ("Crédito Estruturado", "Por Operação", "TARIFA"),  # fora-de-catalogo
]


def _natureza_seed() -> list[dict]:
    rows: list[dict] = []
    for categoria, descricao in _TIPO1_TARIFA:
        rows.append(
            {
                "tenant_id": None,
                "version": 1,
                "fonte": "DRE_OPERACIONAL",
                "categoria": categoria,
                "descricao": descricao,
                "natureza": "TARIFA",
            }
        )
    for categoria, descricao, natureza in _NATUREZA_EXPLICITA:
        rows.append(
            {
                "tenant_id": None,
                "version": 1,
                "fonte": "DRE_OPERACIONAL",
                "categoria": categoria,
                "descricao": descricao,
                "natureza": natureza,
            }
        )
    return rows


def upgrade() -> None:
    # ── wh_bitfin_tarifa_catalogo (dim, por tenant) ─────────────────────────
    op.create_table(
        "wh_bitfin_tarifa_catalogo",
        sa.Column(
            "id", sa.UUID(), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("categoria", sa.String(length=50), nullable=False),
        sa.Column("descricao", sa.String(length=80), nullable=False),
        sa.Column("tipo", sa.Integer(), nullable=False),
        sa.Column(
            "comissionada", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_by_version", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "categoria", "descricao",
            name="uq_wh_bitfin_tarifa_catalogo",
        ),
    )
    op.create_index(
        op.f("ix_wh_bitfin_tarifa_catalogo_tenant_id"),
        "wh_bitfin_tarifa_catalogo",
        ["tenant_id"],
        unique=False,
    )

    # ── wh_bitfin_dre_natureza_rule (de-para de natureza) ───────────────────
    op.create_table(
        "wh_bitfin_dre_natureza_rule",
        sa.Column(
            "id", sa.UUID(), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("fonte", sa.String(length=50), nullable=False),
        sa.Column("categoria", sa.String(length=50), nullable=False),
        sa.Column("descricao", sa.String(length=80), nullable=False),
        sa.Column("natureza", sa.String(length=20), nullable=False),
        sa.Column(
            "valid_from", sa.Date(), nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_wh_bitfin_dre_natureza_rule_tenant_id"),
        "wh_bitfin_dre_natureza_rule",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_wh_bitfin_dre_natureza_rule_lookup",
        "wh_bitfin_dre_natureza_rule",
        ["fonte", "categoria", "descricao", "tenant_id"],
        unique=False,
        postgresql_where=sa.text("valid_until IS NULL"),
    )
    op.create_index(
        "uq_wh_bitfin_dre_natureza_rule_active",
        "wh_bitfin_dre_natureza_rule",
        ["tenant_id", "fonte", "categoria", "descricao"],
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("valid_until IS NULL"),
    )

    # ── colunas no silver wh_dre_mensal (aditivo) ───────────────────────────
    op.add_column(
        "wh_dre_mensal",
        sa.Column("fonte_integracao", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "wh_dre_mensal",
        sa.Column("natureza", sa.String(length=20), nullable=True),
    )
    op.create_index(
        op.f("ix_wh_dre_mensal_fonte_integracao"),
        "wh_dre_mensal",
        ["fonte_integracao"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wh_dre_mensal_natureza"),
        "wh_dre_mensal",
        ["natureza"],
        unique=False,
    )

    # Backfill: tudo que ja existe veio do Bitfin.
    op.execute(
        "UPDATE wh_dre_mensal SET fonte_integracao = 'bitfin' "
        "WHERE fonte_integracao IS NULL"
    )

    # ── seed das 63 regras globais de natureza ──────────────────────────────
    table = sa.table(
        "wh_bitfin_dre_natureza_rule",
        sa.column("tenant_id", sa.UUID()),
        sa.column("version", sa.Integer()),
        sa.column("fonte", sa.String()),
        sa.column("categoria", sa.String()),
        sa.column("descricao", sa.String()),
        sa.column("natureza", sa.String()),
    )
    op.bulk_insert(table, _natureza_seed())


def downgrade() -> None:
    op.drop_index(
        op.f("ix_wh_dre_mensal_natureza"), table_name="wh_dre_mensal"
    )
    op.drop_index(
        op.f("ix_wh_dre_mensal_fonte_integracao"), table_name="wh_dre_mensal"
    )
    op.drop_column("wh_dre_mensal", "natureza")
    op.drop_column("wh_dre_mensal", "fonte_integracao")

    op.drop_index(
        "uq_wh_bitfin_dre_natureza_rule_active",
        table_name="wh_bitfin_dre_natureza_rule",
    )
    op.drop_index(
        "ix_wh_bitfin_dre_natureza_rule_lookup",
        table_name="wh_bitfin_dre_natureza_rule",
    )
    op.drop_index(
        op.f("ix_wh_bitfin_dre_natureza_rule_tenant_id"),
        table_name="wh_bitfin_dre_natureza_rule",
    )
    op.drop_table("wh_bitfin_dre_natureza_rule")

    op.drop_index(
        op.f("ix_wh_bitfin_tarifa_catalogo_tenant_id"),
        table_name="wh_bitfin_tarifa_catalogo",
    )
    op.drop_table("wh_bitfin_tarifa_catalogo")
