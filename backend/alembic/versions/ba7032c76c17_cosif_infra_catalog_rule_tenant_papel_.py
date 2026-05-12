"""cosif_infra: catalog, rule, tenant_papel_classificacao

Cria a infraestrutura de classificacao COSIF agnostica (PR3 da Cota Sub).
Plano em `~/.claude/plans/analise-esse-documento-que-elegant-moth.md`.
Design em `backend/docs/atribuicao-cota-sub-cosif.md`.

3 tabelas:

  cosif_catalog            arvore COSIF oficial (PLANO COSIF II do BACEN)
  cosif_rule               regras estruturais agnosticas (system maintainer A7)
  tenant_papel_classificacao  overrides editaveis livremente por tenant admin

Classificacao e RUNTIME (cascata override -> rule -> pendente). Nao ha coluna
`cosif_codigo` em silvers — decisao 2026-05-11 apos confirmar que raw QiTech
nao traz cosif em nenhum endpoint.

Seed inclui:
- 38 contas COSIF extraidas do balancete oficial REALINVEST mar/2026
- 30+ regras MVP validadas no spike (`scripts/spike_cota_sub_cosif.py`)

Revision ID: ba7032c76c17
Revises: b3d7e1c2a4f5
Create Date: 2026-05-11 21:02:03.383146

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision: str = "ba7032c76c17"
down_revision: str | None = "b3d7e1c2a4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ─── Seed: catalogo COSIF (PLANO COSIF II — REALINVEST mar/2026) ────────────
# Tuplas (codigo, nome, natureza, parent_codigo, nivel, grupo)

CATALOG_SEED: list[tuple[str, str, str, str | None, int, int]] = [
    # Grupo 1 — Ativo
    ("1",                    "CIRCULANTE E REALIZAVEL A LONGO PRAZO",         "D", None,            1, 1),
    ("1.1",                  "DISPONIBILIDADES",                              "D", "1",             2, 1),
    ("1.1.2",                "DEPOSITOS BANCARIOS",                           "D", "1.1",           3, 1),
    ("1.1.2.80",             "BANCOS PRIVADOS - CONTA DEPOSITOS",             "D", "1.1.2",         4, 1),
    ("1.1.2.80.00.001",      "BANCOS CONTA MOVIMENTO",                        "D", "1.1.2.80",      6, 1),
    ("1.1.2.80.00.002",      "BANCO BRADESCO S/A",                            "D", "1.1.2.80",      6, 1),
    ("1.1.2.80.00.007",      "SINGULARE CORRETORA - CONCILIACAO",             "D", "1.1.2.80",      6, 1),
    ("1.2",                  "APLICACOES INTERFINANCEIRAS DE LIQUIDEZ",       "D", "1",             2, 1),
    ("1.2.1.10.05.001",      "LTN - LETRAS DO TESOURO NACIONAL",              "D", "1.2",           6, 1),
    ("1.3",                  "TVM E INSTRUMENTOS FINANC. DERIVATIVOS",        "D", "1",             2, 1),
    ("1.3.1",                "LIVRES",                                        "D", "1.3",           3, 1),
    ("1.3.1.10",             "TITULOS DE RENDA FIXA",                         "D", "1.3.1",         4, 1),
    ("1.3.1.10.07",          "NOTAS DO TESOURO NACIONAL",                     "D", "1.3.1.10",      5, 1),
    ("1.3.1.10.07.001",      "NTN - NOTAS DO TESOURO NACIONAL",               "D", "1.3.1.10.07",   6, 1),
    ("1.3.1.10.16",          "NOTAS DO BANCO CENTRAL",                        "D", "1.3.1.10",      5, 1),
    ("1.3.1.10.16.001",      "NOTA COMERCIAL",                                "D", "1.3.1.10.16",   6, 1),
    ("1.3.1.10.16.002",      "NOTA COMERCIAL - VENCIDOS",                     "D", "1.3.1.10.16",   6, 1),
    ("1.3.1.15",             "COTAS DE FUNDOS DE INVESTIMENTO",               "D", "1.3.1",         4, 1),
    ("1.3.1.15.30",          "COTAS DE FUNDOS MUTUOS DE RENDA FIXA",          "D", "1.3.1.15",      5, 1),
    ("1.3.1.15.30.001",      "COTAS DE FUNDOS DE RENDA FIXA",                 "D", "1.3.1.15.30",   6, 1),
    ("1.6",                  "OPERACOES DE CREDITO",                          "D", "1",             2, 1),
    ("1.6.1",                "EMPRESTIMOS E TITULOS DESCONTADOS",             "D", "1.6",           3, 1),
    ("1.6.1.30",             "TITULOS DESCONTADOS",                           "D", "1.6.1",         4, 1),
    ("1.6.1.30.00.001",      "RECEBIVEIS EM CURSO NORMAL",                    "D", "1.6.1.30",      6, 1),
    ("1.6.1.30.00.002",      "RECEBIVEIS VENCIDOS",                           "D", "1.6.1.30",      6, 1),
    ("1.6.9",                "PROVISAO PARA OP. DE CREDITO (-)",              "C", "1.6",           3, 1),
    ("1.6.9.97.00.001",      "(-) PDD - PROVISAO PARA DEVEDORES DUVIDOSOS",   "C", "1.6.9",         6, 1),
    ("1.8",                  "OUTROS CREDITOS",                               "D", "1",             2, 1),
    ("1.8.4",                "NEGOCIACAO E INTERMEDIACAO DE VALORES",         "D", "1.8",           3, 1),
    ("1.8.4.30",             "DEVEDORES - CONTA LIQUIDACOES PENDENTES",       "D", "1.8.4",         4, 1),
    ("1.8.4.30.00.005",      "AJUSTE DE COMPENSACAO DE COTA",                 "D", "1.8.4.30",      6, 1),
    ("1.9",                  "OUTROS VALORES E BENS",                         "D", "1",             2, 1),
    ("1.9.9",                "DESPESAS ANTECIPADAS",                          "D", "1.9",           3, 1),
    ("1.9.9.10.00",          "DESPESAS ANTECIPADAS",                          "D", "1.9.9",         5, 1),
    # Grupo 4 — Passivo (provisoes a pagar)
    ("4",                    "CIRCULANTE E EXIGIVEL A LONGO PRAZO",           "C", None,            1, 4),
    ("4.9",                  "OUTRAS OBRIGACOES",                             "C", "4",             2, 4),
    ("4.9.1",                "COBRANCA E ARRECADACAO DE TRIBUTOS",            "C", "4.9",           3, 4),
    ("4.9.1.10",             "IOF A RECOLHER",                                "C", "4.9.1",         4, 4),
    ("4.9.1.10.00.001",      "IOF A RECOLHER",                                "C", "4.9.1.10",      6, 4),
    ("4.9.9",                "DIVERSAS",                                      "C", "4.9",           3, 4),
    ("4.9.9.30",             "PROVISAO PARA PAGAMENTOS A EFETUAR",            "C", "4.9.9",         4, 4),
    ("4.9.9.30.50",          "OUTRAS DESPESAS ADMINISTRATIVAS",               "C", "4.9.9.30",      5, 4),
    ("4.9.9.30.50.002",      "AUDITORIA",                                     "C", "4.9.9.30.50",   6, 4),
    ("4.9.9.30.50.003",      "CONSULTORIA ESPECIALIZADA",                     "C", "4.9.9.30.50",   6, 4),
    ("4.9.9.30.50.004",      "BANCO LIQUIDANTE",                              "C", "4.9.9.30.50",   6, 4),
    ("4.9.9.30.50.005",      "SELIC",                                         "C", "4.9.9.30.50",   6, 4),
    ("4.9.9.30.50.008",      "TAXA DE CUSTODIA",                              "C", "4.9.9.30.50",   6, 4),
    ("4.9.9.30.50.021",      "DESPESAS DE COBRANCA",                          "C", "4.9.9.30.50",   6, 4),
    ("4.9.9.30.90",          "OUTROS PAGAMENTOS",                             "C", "4.9.9.30",      5, 4),
    ("4.9.9.30.90.005",      "CREDITOS A CONCILIAR",                          "C", "4.9.9.30.90",   6, 4),
    ("4.9.9.83",             "VALORES A PAGAR A SOC. ADMINISTRADORA",         "C", "4.9.9",         4, 4),
    ("4.9.9.83.00",          "VALORES A PAGAR A SOC. ADMINISTRADORA",         "C", "4.9.9.83",      5, 4),
    ("4.9.9.83.00.001",      "TAXA DE ADMINISTRACAO",                         "C", "4.9.9.83.00",   6, 4),
    ("4.9.9.83.00.004",      "TAXA DE GESTAO",                                "C", "4.9.9.83.00",   6, 4),
    # Grupo 6 — PL (cotas emitidas)
    ("6",                    "PATRIMONIO LIQUIDO",                            "C", None,            1, 6),
    ("6.1",                  "PATRIMONIO LIQUIDO",                            "C", "6",             2, 6),
    ("6.1.1",                "CAPITAL SOCIAL",                                "C", "6.1",           3, 6),
    ("6.1.1.70",             "COTAS DE INVESTIMENTO",                         "C", "6.1.1",         4, 6),
    ("6.1.1.70.20.001",      "PESSOAS FISICAS - EMISSAO",                     "C", "6.1.1.70",      6, 6),
    ("6.1.1.70.30.001",      "PESSOAS JURIDICAS - EMISSAO",                   "C", "6.1.1.70",      6, 6),
    # Grupo 8 — DRE Despesas (acumulado mensal)
    ("8",                    "CONTAS DE RESULTADO DEVEDORAS",                 "D", None,            1, 8),
    ("8.1",                  "DESPESAS OPERACIONAIS",                         "D", "8",             2, 8),
    ("8.1.7",                "DESPESAS ADMINISTRATIVAS",                      "D", "8.1",           3, 8),
    ("8.1.7.54",             "DESPESAS DE SERVICOS DO SISTEMA FINANCEIRO",    "D", "8.1.7",         4, 8),
    ("8.1.7.54.00.004",      "TAXA DE CUSTODIA (DRE)",                        "D", "8.1.7.54",      6, 8),
    ("8.1.7.81",             "DESPESAS DE TAXA DE ADMINISTRACAO DO FUNDO",    "D", "8.1.7",         4, 8),
    ("8.1.7.81.00.001",      "TAXA DE ADMINISTRACAO (DRE)",                   "D", "8.1.7.81",      6, 8),
    ("8.1.7.81.00.004",      "TAXA DE GESTAO (DRE)",                          "D", "8.1.7.81",      6, 8),
]


# ─── Seed: regras estruturais MVP (validadas no spike) ──────────────────────
# Tuplas (silver_origin, predicate_jsonb, cosif_codigo, classe, priority,
#         confidence, rule_id_humano)
#
# Predicate JSON suportado pelo classifier:
#   {"field":"<col>", "op":"eq|ne|in|contains|starts_with|ends_with|qtde_signal", "value":<v>}
#   {"all":[...predicates...]}    -> AND
#   {"any":[...predicates...]}    -> OR
#
# Ordem: priority desc (mais especifica primeiro). Empate por
# rule_id_humano asc.

RULE_SEED: list[tuple[str, dict, str, str | None, int, str, str]] = [
    # ─── wh_saldo_tesouraria — sempre vai pra bancos movimento ────────────
    ("wh_saldo_tesouraria", {"all": []}, "1.1.2.80.00.001", None, 10, "alta",
     "tesouraria.bancos_movimento"),

    # ─── wh_posicao_compromissada — assumindo LTN como default ────────────
    ("wh_posicao_compromissada", {"all": []}, "1.2.1.10.05.001", None, 10, "media",
     "compromissada.ltn_default"),

    # ─── wh_posicao_renda_fixa — cotas emitidas (qtde<0) ──────────────────
    ("wh_posicao_renda_fixa",
     {"all": [{"field": "quantidade", "op": "qtde_signal", "value": "negative"},
              {"field": "nome_do_papel", "op": "starts_with", "value": "SR"}]},
     "6.1.1.70.30.001", "senior", 100, "alta",
     "rf.cota_sr_emitida"),
    ("wh_posicao_renda_fixa",
     {"all": [{"field": "quantidade", "op": "qtde_signal", "value": "negative"},
              {"field": "nome_do_papel", "op": "starts_with", "value": "MEZ"}]},
     "6.1.1.70.30.001", "mezanino", 100, "alta",
     "rf.cota_mez_emitida"),
    ("wh_posicao_renda_fixa",
     {"all": [{"field": "quantidade", "op": "qtde_signal", "value": "negative"},
              {"field": "nome_do_papel", "op": "starts_with", "value": "SUB"}]},
     "6.1.1.70.30.001", "subordinado", 100, "alta",
     "rf.cota_sub_emitida"),
    # ─── wh_posicao_renda_fixa — contrapartida positiva (compensacao) ────
    # NULL cosif = compensação grupos 3/9 (não classificada na arvore principal).
    ("wh_posicao_renda_fixa",
     {"all": [{"field": "quantidade", "op": "qtde_signal", "value": "positive"},
              {"any": [{"field": "nome_do_papel", "op": "starts_with", "value": "SR"},
                       {"field": "nome_do_papel", "op": "starts_with", "value": "MEZ"},
                       {"field": "nome_do_papel", "op": "starts_with", "value": "SUB"}]}]},
     None, "compensacao", 90, "media",
     "rf.contrapartida_compensacao"),
    # ─── wh_posicao_renda_fixa — ativos reais ────────────────────────────
    ("wh_posicao_renda_fixa",
     {"all": [{"field": "nome_do_papel", "op": "contains", "value": "NTN"}]},
     "1.3.1.10.07.001", None, 50, "alta", "rf.ntn"),
    ("wh_posicao_renda_fixa",
     {"any": [{"field": "nome_do_papel", "op": "contains", "value": "NCPX"},
              {"field": "nome_do_papel", "op": "contains", "value": "NOTA"}]},
     "1.3.1.10.16.001", None, 50, "media", "rf.nota_comercial"),

    # ─── wh_posicao_cota_fundo ───────────────────────────────────────────
    ("wh_posicao_cota_fundo",
     {"field": "ativo_nome", "op": "contains_ci", "value": "VENCER"},
     "1.6.1.30.00.001", None, 50, "alta", "cf.dc_a_vencer"),
    ("wh_posicao_cota_fundo",
     {"field": "ativo_nome", "op": "contains_ci", "value": "VENCIDO"},
     "1.6.1.30.00.002", None, 50, "alta", "cf.dc_vencidos"),
    ("wh_posicao_cota_fundo", {"all": []}, "1.3.1.15.30.001", None, 10, "media", "cf.di_rf_default"),

    # ─── wh_posicao_outros_ativos ────────────────────────────────────────
    ("wh_posicao_outros_ativos",
     {"field": "codigo", "op": "eq", "value": "PDD"},
     "1.6.9.97.00.001", None, 100, "alta", "oa.pdd"),
    ("wh_posicao_outros_ativos",
     {"all": []}, "1.8.4.30.00.005", None, 10, "media", "oa.ajuste_compensacao_default"),

    # ─── wh_cpr_movimento — em ordem de specificity ──────────────────────
    # (1) Aporte
    ("wh_cpr_movimento",
     {"field": "historico_traduzido", "op": "contains_ci", "value": "APORTE"},
     "6.1.1.70.30.001", None, 100, "alta", "cpr.aporte"),
    # (2) Liquidados
    ("wh_cpr_movimento",
     {"field": "historico_traduzido", "op": "contains_ci", "value": "LIQUIDADOS"},
     "1.8.4.30.00.005", None, 95, "alta", "cpr.liquidados"),
    # (3) Diferimento (Ativo antecipado)
    ("wh_cpr_movimento",
     {"any": [{"field": "historico_traduzido", "op": "contains_ci", "value": "DIFERIMENTO"},
              {"field": "historico_traduzido", "op": "contains_ci", "value": "DIFERIR"}]},
     "1.9.9.10.00", None, 90, "alta", "cpr.diferimento"),
    # (4) IOF
    ("wh_cpr_movimento",
     {"field": "historico_traduzido", "op": "contains_ci", "value": "IOF"},
     "4.9.1.10.00.001", None, 85, "alta", "cpr.iof"),
    # (5) Creditos a Conciliar
    ("wh_cpr_movimento",
     {"field": "historico_traduzido", "op": "contains_ci", "value": "CONCILIAR"},
     "4.9.9.30.90.005", None, 80, "alta", "cpr.creditos_conciliar"),
    # (6) APROPRIADA — DRE competência grupo 8
    ("wh_cpr_movimento",
     {"all": [{"field": "historico_traduzido", "op": "contains_ci", "value": "APROPRIADA"},
              {"field": "historico_traduzido", "op": "contains_ci", "value": "CUSTODIA"}]},
     "8.1.7.54.00.004", None, 75, "alta", "cpr.dre.custodia"),
    ("wh_cpr_movimento",
     {"all": [{"field": "historico_traduzido", "op": "contains_ci", "value": "APROPRIADA"},
              {"field": "historico_traduzido", "op": "contains_ci", "value": "ADMINISTRACAO"}]},
     "8.1.7.81.00.001", None, 75, "alta", "cpr.dre.adm"),
    ("wh_cpr_movimento",
     {"all": [{"field": "historico_traduzido", "op": "contains_ci", "value": "APROPRIADA"},
              {"field": "historico_traduzido", "op": "contains_ci", "value": "GESTAO"}]},
     "8.1.7.81.00.004", None, 75, "alta", "cpr.dre.gestao"),
    # (7) "Despesa de X com pagamento" / "Despesas com X em" — Passivo 4.9.x
    ("wh_cpr_movimento",
     {"field": "historico_traduzido", "op": "contains_ci", "value": "AUDITORIA"},
     "4.9.9.30.50.002", None, 50, "alta", "cpr.passivo.auditoria"),
    ("wh_cpr_movimento",
     {"field": "historico_traduzido", "op": "contains_ci", "value": "CUSTODIA"},
     "4.9.9.30.50.008", None, 50, "alta", "cpr.passivo.custodia"),
    ("wh_cpr_movimento",
     {"field": "historico_traduzido", "op": "contains_ci", "value": "BANCO LIQUIDANTE"},
     "4.9.9.30.50.004", None, 50, "alta", "cpr.passivo.banco_liquidante"),
    ("wh_cpr_movimento",
     {"field": "historico_traduzido", "op": "contains_ci", "value": "SELIC"},
     "4.9.9.30.50.005", None, 50, "alta", "cpr.passivo.selic"),
    ("wh_cpr_movimento",
     {"field": "historico_traduzido", "op": "contains_ci", "value": "COBRANCA"},
     "4.9.9.30.50.021", None, 50, "alta", "cpr.passivo.cobranca"),
    ("wh_cpr_movimento",
     {"field": "historico_traduzido", "op": "contains_ci", "value": "CONSULTORIA"},
     "4.9.9.30.50.003", None, 50, "alta", "cpr.passivo.consultoria"),
    ("wh_cpr_movimento",
     {"field": "historico_traduzido", "op": "contains_ci", "value": "ADMINISTRACAO"},
     "4.9.9.83.00.001", None, 50, "alta", "cpr.passivo.adm"),
    ("wh_cpr_movimento",
     {"field": "historico_traduzido", "op": "contains_ci", "value": "GESTAO"},
     "4.9.9.83.00.004", None, 50, "alta", "cpr.passivo.gestao"),
    # (8) Fallback CPR
    ("wh_cpr_movimento", {"all": []}, "4.9.9.30", None, 10, "baixa", "cpr.outras_provisoes"),
]


def upgrade() -> None:
    # ─── 1) cosif_catalog ────────────────────────────────────────────────
    op.create_table(
        "cosif_catalog",
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("nome", sa.String(length=200), nullable=False),
        sa.Column("natureza", sa.String(length=1), nullable=False),
        sa.Column("parent_codigo", sa.String(length=20), nullable=True),
        sa.Column("nivel", sa.SmallInteger(), nullable=False),
        sa.Column("grupo", sa.SmallInteger(), nullable=False),
        sa.Column(
            "plano_id", sa.SmallInteger(),
            server_default=sa.text("5"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("codigo"),
        sa.CheckConstraint("natureza IN ('D','C')", name="ck_cosif_catalog_natureza"),
        sa.ForeignKeyConstraint(
            ["parent_codigo"], ["cosif_catalog.codigo"],
            name="fk_cosif_catalog_parent", ondelete="RESTRICT",
        ),
    )
    op.create_index(
        op.f("ix_cosif_catalog_parent_codigo"),
        "cosif_catalog", ["parent_codigo"], unique=False,
    )
    op.create_index(
        op.f("ix_cosif_catalog_grupo"),
        "cosif_catalog", ["grupo"], unique=False,
    )

    # ─── 2) cosif_rule ───────────────────────────────────────────────────
    op.create_table(
        "cosif_rule",
        sa.Column(
            "id", sa.UUID(),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column("silver_origin", sa.String(length=50), nullable=False),
        sa.Column("predicate_jsonb", postgresql.JSONB(), nullable=False),
        # NULL = regra marca como "pendente_classificacao" (caso da
        # contrapartida positiva de compensacao 3/9 — comportamento esperado).
        sa.Column("cosif_codigo", sa.String(length=20), nullable=True),
        sa.Column("classe_sr_mez_sub", sa.String(length=20), nullable=True),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column(
            "confidence", sa.String(length=10),
            server_default=sa.text("'alta'"), nullable=False,
        ),
        sa.Column("rule_id_humano", sa.String(length=80), nullable=False),
        sa.Column("valid_from", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column(
            "classifier_version", sa.String(length=20),
            server_default=sa.text("'1.0.0'"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id_humano", name="uq_cosif_rule_rule_id_humano"),
        sa.CheckConstraint(
            "confidence IN ('alta','media','baixa')",
            name="ck_cosif_rule_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["cosif_codigo"], ["cosif_catalog.codigo"],
            name="fk_cosif_rule_codigo", ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_cosif_rule_busca",
        "cosif_rule",
        ["silver_origin", "priority"],
        unique=False,
    )

    # ─── 3) tenant_papel_classificacao ───────────────────────────────────
    op.create_table(
        "tenant_papel_classificacao",
        sa.Column(
            "id", sa.UUID(),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("fundo_id", sa.UUID(), nullable=False),
        sa.Column("silver_origin", sa.String(length=50), nullable=False),
        sa.Column("identificador", sa.String(length=80), nullable=False),
        sa.Column("cosif_override", sa.String(length=20), nullable=False),
        sa.Column("classe_sr_mez_sub", sa.String(length=20), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "fundo_id", "silver_origin", "identificador",
            name="uq_tenant_papel_classificacao",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fundo_id"], ["cadastros_unidade_administrativa.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cosif_override"], ["cosif_catalog.codigo"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_tenant_papel_classificacao_lookup",
        "tenant_papel_classificacao",
        ["tenant_id", "fundo_id", "silver_origin", "identificador"],
        unique=False,
    )

    # ─── 4) Seed: cosif_catalog ──────────────────────────────────────────
    # Ordem importante: parents antes dos filhos (FK self-ref). Lista ja
    # ordenada manualmente.
    catalog_table = sa.table(
        "cosif_catalog",
        sa.column("codigo", sa.String),
        sa.column("nome", sa.String),
        sa.column("natureza", sa.String),
        sa.column("parent_codigo", sa.String),
        sa.column("nivel", sa.SmallInteger),
        sa.column("grupo", sa.SmallInteger),
    )
    op.bulk_insert(catalog_table, [
        {
            "codigo": c, "nome": n, "natureza": nat, "parent_codigo": p,
            "nivel": niv, "grupo": g,
        }
        for (c, n, nat, p, niv, g) in CATALOG_SEED
    ])

    # ─── 5) Seed: cosif_rule ─────────────────────────────────────────────
    rule_table = sa.table(
        "cosif_rule",
        sa.column("silver_origin", sa.String),
        sa.column("predicate_jsonb", postgresql.JSONB),
        sa.column("cosif_codigo", sa.String),
        sa.column("classe_sr_mez_sub", sa.String),
        sa.column("priority", sa.SmallInteger),
        sa.column("confidence", sa.String),
        sa.column("rule_id_humano", sa.String),
    )
    op.bulk_insert(rule_table, [
        {
            "silver_origin": silv,
            "predicate_jsonb": pred,
            "cosif_codigo": cosif,
            "classe_sr_mez_sub": classe,
            "priority": prio,
            "confidence": conf,
            "rule_id_humano": rid,
        }
        for (silv, pred, cosif, classe, prio, conf, rid) in RULE_SEED
    ])


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_papel_classificacao_lookup",
        table_name="tenant_papel_classificacao",
    )
    op.drop_table("tenant_papel_classificacao")
    op.drop_index("ix_cosif_rule_busca", table_name="cosif_rule")
    op.drop_table("cosif_rule")
    op.drop_index(
        op.f("ix_cosif_catalog_grupo"), table_name="cosif_catalog",
    )
    op.drop_index(
        op.f("ix_cosif_catalog_parent_codigo"), table_name="cosif_catalog",
    )
    op.drop_table("cosif_catalog")
