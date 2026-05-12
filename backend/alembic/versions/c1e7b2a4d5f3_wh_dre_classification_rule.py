"""wh_dre_classification_rule + seed das 77 regras globais

Substitui o lookup ANALYTICS.dbo.DREClassificacao (A7-especifico) por
tabela canonica no gr_db, com suporte a override por tenant e
versionamento (CLAUDE.md secao 14.3).

Seed inicial = export das 77 regras hoje em producao na A7 Credit, todas
com tenant_id=NULL (regras globais). Tenant que precisar override cria
sua propria row com tenant_id setado.

CLAUDE.md secao 13: o adapter Bitfin (a partir de v2.0.0) deixa de
depender de ANALYTICS no caminho critico do DRE. A regra de
classificacao agora mora aqui.

Revision ID: c1e7b2a4d5f3
Revises: ba7032c76c17
Create Date: 2026-05-12 09:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1e7b2a4d5f3"
down_revision: str | None = "ba7032c76c17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Seed: 77 regras extraidas de ANALYTICS.dbo.DREClassificacao (A7 Credit prod
# em 2026-05-12). Tuplas (fonte, categoria, grupo_dre, subgrupo, ordem_grupo,
# ativo). Tenant_id NULL (regra global) + version=1.
#
# 7 regras com ativo=False sao categorias EXCLUIDO de CONTAS_A_PAGAR
# (Cartao de Credito, Estorno, Investimento, etc) — nao contam no DRE
# mas mantemos no seed por traceability (mapper deve respeitar ativo).
RULES_SEED: list[tuple[str, str, str, str, int, bool]] = [
    # ─── DRE_OPERACIONAL (Bloco 1: receitas/custos operacionais) ─────────────
    ("DRE_OPERACIONAL", "Operação",            "RECEITA_OPERACIONAL", "Operação",          1, True),
    ("DRE_OPERACIONAL", "Crédito Estruturado", "RECEITA_OPERACIONAL", "Crédito Estruturado", 2, True),
    ("DRE_OPERACIONAL", "Recompra",            "RECEITA_OPERACIONAL", "Recompra",          3, True),
    ("DRE_OPERACIONAL", "Título",              "RECEITA_OPERACIONAL", "Título",            4, True),
    ("DRE_OPERACIONAL", "Conta Gráfica",       "RECEITA_OPERACIONAL", "Conta Gráfica",     5, True),
    ("DRE_OPERACIONAL", "PDD",                 "PROVISAO_PDD",        "PDD",               6, True),
    ("DRE_OPERACIONAL", "Despesa",             "RECEITA_OPERACIONAL", "Despesa",           7, True),

    # ─── CONTAS_A_PAGAR (Bloco 2: despesas administrativas) ──────────────────
    # Pessoal
    ("CONTAS_A_PAGAR", "13º Salário",   "DESPESA_ADMINISTRATIVA", "Pessoal", 8, True),
    ("CONTAS_A_PAGAR", "Férias",        "DESPESA_ADMINISTRATIVA", "Pessoal", 8, True),
    ("CONTAS_A_PAGAR", "FGTS",          "DESPESA_ADMINISTRATIVA", "Pessoal", 8, True),
    ("CONTAS_A_PAGAR", "Funcionários",  "DESPESA_ADMINISTRATIVA", "Pessoal", 8, True),
    ("CONTAS_A_PAGAR", "Gratificação",  "DESPESA_ADMINISTRATIVA", "Pessoal", 8, True),
    ("CONTAS_A_PAGAR", "Hora Extra",    "DESPESA_ADMINISTRATIVA", "Pessoal", 8, True),
    ("CONTAS_A_PAGAR", "INSS",          "DESPESA_ADMINISTRATIVA", "Pessoal", 8, True),
    ("CONTAS_A_PAGAR", "Pró-Labore",    "DESPESA_ADMINISTRATIVA", "Pessoal", 8, True),
    ("CONTAS_A_PAGAR", "Reembolso",     "DESPESA_ADMINISTRATIVA", "Pessoal", 8, True),
    ("CONTAS_A_PAGAR", "Rescisão",      "DESPESA_ADMINISTRATIVA", "Pessoal", 8, True),
    ("CONTAS_A_PAGAR", "Salário",       "DESPESA_ADMINISTRATIVA", "Pessoal", 8, True),
    ("CONTAS_A_PAGAR", "Sindicato",     "DESPESA_ADMINISTRATIVA", "Pessoal", 8, True),

    # Beneficios
    ("CONTAS_A_PAGAR", "Assistência Médica",      "DESPESA_ADMINISTRATIVA", "Beneficios", 8, True),
    ("CONTAS_A_PAGAR", "Assistência Odontológica","DESPESA_ADMINISTRATIVA", "Beneficios", 8, True),
    ("CONTAS_A_PAGAR", "Medicina Ocupacional",    "DESPESA_ADMINISTRATIVA", "Beneficios", 8, True),
    ("CONTAS_A_PAGAR", "Refeição",                "DESPESA_ADMINISTRATIVA", "Beneficios", 8, True),
    ("CONTAS_A_PAGAR", "Vale Refeição",           "DESPESA_ADMINISTRATIVA", "Beneficios", 8, True),
    ("CONTAS_A_PAGAR", "Vale Transporte",         "DESPESA_ADMINISTRATIVA", "Beneficios", 8, True),

    # Tributos e Impostos
    ("CONTAS_A_PAGAR", "COFINS",              "DESPESA_ADMINISTRATIVA", "Tributos e Impostos", 8, True),
    ("CONTAS_A_PAGAR", "CSLL",                "DESPESA_ADMINISTRATIVA", "Tributos e Impostos", 8, True),
    ("CONTAS_A_PAGAR", "DAS",                 "DESPESA_ADMINISTRATIVA", "Tributos e Impostos", 8, True),
    ("CONTAS_A_PAGAR", "Despesas com IOF",    "DESPESA_ADMINISTRATIVA", "Tributos e Impostos", 8, True),
    ("CONTAS_A_PAGAR", "Imposto",             "DESPESA_ADMINISTRATIVA", "Tributos e Impostos", 8, True),
    ("CONTAS_A_PAGAR", "IOF",                 "DESPESA_ADMINISTRATIVA", "Tributos e Impostos", 8, True),
    ("CONTAS_A_PAGAR", "IRPF",                "DESPESA_ADMINISTRATIVA", "Tributos e Impostos", 8, True),
    ("CONTAS_A_PAGAR", "IRPJ",                "DESPESA_ADMINISTRATIVA", "Tributos e Impostos", 8, True),
    ("CONTAS_A_PAGAR", "IRRF",                "DESPESA_ADMINISTRATIVA", "Tributos e Impostos", 8, True),
    ("CONTAS_A_PAGAR", "Pagamento de IOF",    "DESPESA_ADMINISTRATIVA", "Tributos e Impostos", 8, True),
    ("CONTAS_A_PAGAR", "PIS",                 "DESPESA_ADMINISTRATIVA", "Tributos e Impostos", 8, True),
    ("CONTAS_A_PAGAR", "Taxas Governamentais","DESPESA_ADMINISTRATIVA", "Tributos e Impostos", 8, True),

    # Servicos de Terceiros
    ("CONTAS_A_PAGAR", "Assistência Contábil e Fiscal","DESPESA_ADMINISTRATIVA", "Servicos de Terceiros", 8, True),
    ("CONTAS_A_PAGAR", "Consulta Financeira",         "DESPESA_ADMINISTRATIVA", "Servicos de Terceiros", 8, True),
    ("CONTAS_A_PAGAR", "Custas de Cartório",          "DESPESA_ADMINISTRATIVA", "Servicos de Terceiros", 8, True),
    ("CONTAS_A_PAGAR", "Custas Processuais",          "DESPESA_ADMINISTRATIVA", "Servicos de Terceiros", 8, True),
    ("CONTAS_A_PAGAR", "Honorário Advocatício",       "DESPESA_ADMINISTRATIVA", "Servicos de Terceiros", 8, True),
    ("CONTAS_A_PAGAR", "Informática",                 "DESPESA_ADMINISTRATIVA", "Servicos de Terceiros", 8, True),
    ("CONTAS_A_PAGAR", "Serv. Prest. Pessoa Física",  "DESPESA_ADMINISTRATIVA", "Servicos de Terceiros", 8, True),
    ("CONTAS_A_PAGAR", "Serv. Prest. Pessoa Jurídica","DESPESA_ADMINISTRATIVA", "Servicos de Terceiros", 8, True),

    # Ocupacao e Utilidades
    ("CONTAS_A_PAGAR", "Aluguel",                       "DESPESA_ADMINISTRATIVA", "Ocupacao e Utilidades", 8, True),
    ("CONTAS_A_PAGAR", "Condomínio",                    "DESPESA_ADMINISTRATIVA", "Ocupacao e Utilidades", 8, True),
    ("CONTAS_A_PAGAR", "Energia Elétrica",              "DESPESA_ADMINISTRATIVA", "Ocupacao e Utilidades", 8, True),
    ("CONTAS_A_PAGAR", "Internet",                      "DESPESA_ADMINISTRATIVA", "Ocupacao e Utilidades", 8, True),
    ("CONTAS_A_PAGAR", "Pagamento de Conta de Consumo", "DESPESA_ADMINISTRATIVA", "Ocupacao e Utilidades", 8, True),
    ("CONTAS_A_PAGAR", "Telefone",                      "DESPESA_ADMINISTRATIVA", "Ocupacao e Utilidades", 8, True),

    # Assinaturas e Sistemas
    ("CONTAS_A_PAGAR", "Assinatura de Produto/Serviço", "DESPESA_ADMINISTRATIVA", "Assinaturas e Sistemas", 8, True),
    ("CONTAS_A_PAGAR", "Filiação",                      "DESPESA_ADMINISTRATIVA", "Assinaturas e Sistemas", 8, True),

    # Transporte e Veiculos
    ("CONTAS_A_PAGAR", "Combustível", "DESPESA_ADMINISTRATIVA", "Transporte e Veiculos", 8, True),
    ("CONTAS_A_PAGAR", "Condução",    "DESPESA_ADMINISTRATIVA", "Transporte e Veiculos", 8, True),
    ("CONTAS_A_PAGAR", "KM Rodado",   "DESPESA_ADMINISTRATIVA", "Transporte e Veiculos", 8, True),
    ("CONTAS_A_PAGAR", "Pedágio",     "DESPESA_ADMINISTRATIVA", "Transporte e Veiculos", 8, True),

    # Viagens e Deslocamentos
    ("CONTAS_A_PAGAR", "Estacionamento", "DESPESA_ADMINISTRATIVA", "Viagens e Deslocamentos", 8, True),

    # Marketing e Publicidade
    ("CONTAS_A_PAGAR", "Brindes",         "DESPESA_ADMINISTRATIVA", "Marketing e Publicidade", 8, True),
    ("CONTAS_A_PAGAR", "Confraternização","DESPESA_ADMINISTRATIVA", "Marketing e Publicidade", 8, True),
    ("CONTAS_A_PAGAR", "Marketing",       "DESPESA_ADMINISTRATIVA", "Marketing e Publicidade", 8, True),

    # Outros
    ("CONTAS_A_PAGAR", "Afiliação",            "DESPESA_ADMINISTRATIVA", "Outros", 8, True),
    ("CONTAS_A_PAGAR", "Comissão",             "DESPESA_ADMINISTRATIVA", "Outros", 8, True),
    ("CONTAS_A_PAGAR", "Material de Copa",     "DESPESA_ADMINISTRATIVA", "Outros", 8, True),
    ("CONTAS_A_PAGAR", "Material de Escritório","DESPESA_ADMINISTRATIVA", "Outros", 8, True),
    ("CONTAS_A_PAGAR", "Material de Limpeza",  "DESPESA_ADMINISTRATIVA", "Outros", 8, True),
    ("CONTAS_A_PAGAR", "Móveis/Utensílios",    "DESPESA_ADMINISTRATIVA", "Outros", 8, True),
    ("CONTAS_A_PAGAR", "Seguro de Vida em Grupo","DESPESA_ADMINISTRATIVA", "Outros", 8, True),
    ("CONTAS_A_PAGAR", "Seguro Empresarial",   "DESPESA_ADMINISTRATIVA", "Outros", 8, True),

    # ─── COMISSAO (Bloco 3: comissoes comerciais) ────────────────────────────
    ("COMISSAO", "Comissao de Consultor", "COMISSAO_COMERCIAL", "Comissoes Comerciais", 9, True),

    # ─── EXCLUIDO (categorias CONTAS_A_PAGAR que NAO contam no DRE) ──────────
    # ativo=False; mapper deve respeitar e descartar.
    ("CONTAS_A_PAGAR", "Cartão de Crédito",       "EXCLUIDO", "Excluido", 0, False),
    ("CONTAS_A_PAGAR", "Contribuição/Doação",     "EXCLUIDO", "Excluido", 0, False),
    ("CONTAS_A_PAGAR", "Estorno",                 "EXCLUIDO", "Excluido", 0, False),
    ("CONTAS_A_PAGAR", "Investimento",            "EXCLUIDO", "Excluido", 0, False),
    ("CONTAS_A_PAGAR", "Outras Tarifas Bancárias","EXCLUIDO", "Excluido", 0, False),
    ("CONTAS_A_PAGAR", "Pagamento Operacional",   "EXCLUIDO", "Excluido", 0, False),
    ("CONTAS_A_PAGAR", "Tomada de Recursos",      "EXCLUIDO", "Excluido", 0, False),
]


def upgrade() -> None:
    op.create_table(
        "wh_dre_classification_rule",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("fonte", sa.String(length=50), nullable=False),
        sa.Column("categoria", sa.String(length=200), nullable=False),
        sa.Column("grupo_dre", sa.String(length=50), nullable=False),
        sa.Column("subgrupo", sa.String(length=100), nullable=False),
        sa.Column("ordem_grupo", sa.Integer(), nullable=False),
        sa.Column(
            "ativo", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "valid_from",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_wh_dre_classification_rule_tenant_id"),
        "wh_dre_classification_rule",
        ["tenant_id"],
        unique=False,
    )
    # Lookup canonico do classifier.
    op.create_index(
        "ix_wh_dre_classification_rule_lookup",
        "wh_dre_classification_rule",
        ["fonte", "categoria", "tenant_id"],
        unique=False,
        postgresql_where=sa.text("valid_until IS NULL"),
    )
    # Garante 1 regra ATIVA por (tenant_id, fonte, categoria). NULLS NOT
    # DISTINCT trata tenant_id NULL como comparavel (Postgres 15+).
    op.create_index(
        "uq_wh_dre_classification_rule_active",
        "wh_dre_classification_rule",
        ["tenant_id", "fonte", "categoria"],
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("valid_until IS NULL"),
    )

    # Seed: insert das 77 regras globais (tenant_id=NULL, version=1).
    table = sa.table(
        "wh_dre_classification_rule",
        sa.column("tenant_id", sa.UUID()),
        sa.column("version", sa.Integer()),
        sa.column("fonte", sa.String()),
        sa.column("categoria", sa.String()),
        sa.column("grupo_dre", sa.String()),
        sa.column("subgrupo", sa.String()),
        sa.column("ordem_grupo", sa.Integer()),
        sa.column("ativo", sa.Boolean()),
    )
    op.bulk_insert(
        table,
        [
            {
                "tenant_id": None,
                "version": 1,
                "fonte": fonte,
                "categoria": categoria,
                "grupo_dre": grupo_dre,
                "subgrupo": subgrupo,
                "ordem_grupo": ordem_grupo,
                "ativo": ativo,
            }
            for fonte, categoria, grupo_dre, subgrupo, ordem_grupo, ativo in RULES_SEED
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "uq_wh_dre_classification_rule_active",
        table_name="wh_dre_classification_rule",
    )
    op.drop_index(
        "ix_wh_dre_classification_rule_lookup",
        table_name="wh_dre_classification_rule",
    )
    op.drop_index(
        op.f("ix_wh_dre_classification_rule_tenant_id"),
        table_name="wh_dre_classification_rule",
    )
    op.drop_table("wh_dre_classification_rule")
