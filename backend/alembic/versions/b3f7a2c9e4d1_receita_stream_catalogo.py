"""Catalogo de receitas operacionais caixa-fiel: streams + fato.

PR 1 do catalogo de receitas (decisao 2026-06-10, pos-morte da DRE natureza):

- wh_bitfin_receita_stream    -- dim de STREAMS de receita (rotas de caixa),
                                 global/override, versionada, seed de 15
                                 streams nas 9 familias mapeadas.
- wh_receita_operacional      -- fato silver canonico (Auditable), populado
                                 pelo ETL (PR 2) a partir do catalogo.

Fontes caixa-fieis (NUNCA DemonstrativoDeResultado): Titulo,
ContaCorrenteLancamento, RecompraResultado/Item, OperacaoRentabilidade.

Revision ID: b3f7a2c9e4d1
Revises: 2e4aa7fef995
Create Date: 2026-06-10
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "b3f7a2c9e4d1"
down_revision: str | Sequence[str] | None = "2e4aa7fef995"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VALID_FROM = date(2026, 6, 10)

# Codigos de tarifa de servico da conta grafica (debitos ao cliente que sao
# receita nossa). Mantidos em sync com ContaCorrenteCategoria do Bitfin.
_CODIGOS_TARIFA_SERVICO = [
    "008",  # Tarifa de Prorrogacao de Titulo
    "009",  # Tarifa de Abatimento
    "010",  # Tarifa de Baixa de Titulo
    "011",  # Tarifa de Baixa por Protesto
    "012",  # Tarifa de Protesto
    "013",  # Tarifa de Sustacao de Protesto
    "037",  # Tarifa de Nao Protesto
    "050",  # Tarifa de Renovacao Cadastral
    "070",  # Tarifa de Documentos Digitais
    "073",  # Tarifa de Baixa por Decurso de Prazo
    "077",  # Tarifa de TED
    "078",  # Tarifa de Alteracao de Dados
    "084",  # Tarifa de Liquidacao
    "089",  # Tarifa Bancaria de Cancelamento de Abatimento
    "090",  # Tarifa de Negativacao
    "091",  # Tarifa de Cancelamento de Negativacao
    "092",  # Tarifa de PIX
    "094",  # Tarifa de Registro de Recebivel
    "096",  # Tarifa de Liquidacao em Cartorio
    "097",  # Tarifa de Consulta Fiscal
]

# (stream_key, familia, natureza, fonte_tabela, criterio, grao,
#  retido_na_fonte, descricao, notes)
_SEED: list[tuple] = [
    # ── Mora na liquidacao (Titulo: pgto - liquido; split via percentuais
    #    do ProcedimentoDeCobranca como PARAMETRO) ─────────────────────────
    (
        "mora_liquidacao_juros", "mora_liquidacao", "JUROS_MORA", "Titulo",
        {"situacao": 1, "siglas": ["DM", "DS", "NP"], "produto_de_risco": True,
         "split": "juros"},
        "titulo", False,
        "Juros de mora pagos na liquidacao do titulo",
        "Total caixa = ValorDoPagamento - ValorLiquido (>0, pago apos "
        "DataDeVencimentoEfetiva). Split juros x multa proporcional aos "
        "percentuais do ProcedimentoDeCobranca — parametro, nunca valor.",
    ),
    (
        "mora_liquidacao_multa", "mora_liquidacao", "MULTA_MORA", "Titulo",
        {"situacao": 1, "siglas": ["DM", "DS", "NP"], "produto_de_risco": True,
         "split": "multa"},
        "titulo", False,
        "Multa por atraso paga na liquidacao do titulo",
        None,
    ),
    # ── Mora de prorrogacao (conta grafica; titulo em ComplementoInterno
    #    'SIGLA=TituloId'; DISJUNTO da mora de liquidacao — titulo prorrogado
    #    liquida a face) ────────────────────────────────────────────────────
    (
        "prorrogacao_juros", "mora_prorrogacao", "JUROS_MORA",
        "ContaCorrenteLancamento", {"codigos": ["028"]}, "lancamento", False,
        "Juros de Prorrogacao de Titulo (cod 028)",
        "TituloId extraido de ComplementoInterno ('DM=104331').",
    ),
    (
        "prorrogacao_multa", "mora_prorrogacao", "MULTA_MORA",
        "ContaCorrenteLancamento", {"codigos": ["151"]}, "lancamento", False,
        "Multa de Prorrogacao de Titulo (cod 151)",
        None,
    ),
    # ── Mora de cartorio / acertos ──────────────────────────────────────────
    (
        "cartorio_juros", "mora_cartorio", "JUROS_MORA",
        "ContaCorrenteLancamento", {"codigos": ["024"]}, "lancamento", False,
        "Juros por Pagamento em Cartorio (cod 024)",
        None,
    ),
    (
        "diferenca_pagamento", "mora_acerto", "JUROS_MORA",
        "ContaCorrenteLancamento", {"codigos": ["025"]}, "lancamento", False,
        "Diferenca no Pagamento de Titulo (cod 025)",
        None,
    ),
    # ── Recompra (RecompraResultado, Efetivada=1; liquidacao financeira via
    #    PagamentoOperacional Pago=1 — tipicamente netting contra liquido de
    #    operacao nova) ────────────────────────────────────────────────────
    (
        "recompra_juros", "recompra", "JUROS_MORA", "RecompraResultado",
        {"campo": "TotalDeJuros", "efetivada": True}, "recompra", False,
        "Juros cobrados na recompra de titulos",
        "Quebra por titulo via RecompraItem.ValorDeJuros.",
    ),
    (
        "recompra_multa", "recompra", "MULTA_MORA", "RecompraResultado",
        {"campo": "TotalDeMulta", "efetivada": True}, "recompra", False,
        "Multa cobrada na recompra de titulos",
        None,
    ),
    (
        "recompra_desagio", "recompra", "DESAGIO", "RecompraResultado",
        {"campo": "TotalDeDesagio", "efetivada": True}, "recompra", False,
        "Desagio cobrado na recompra de titulos",
        None,
    ),
    # ── Operacao (OperacaoRentabilidade: retido do liquido na efetivacao =
    #    caixa por construcao) ───────────────────────────────────────────────
    (
        "desagio_operacao", "operacao", "DESAGIO", "OperacaoRentabilidade",
        {"descricao_eq": "Deságio", "efetivada": True}, "operacao", True,
        "Desagio da antecipacao (retido do liquido)",
        "Quebra por titulo via OperacaoItem.ValorDeJuros quando necessario.",
    ),
    (
        "tarifa_operacao", "operacao", "TARIFA", "OperacaoRentabilidade",
        {"descricao_not_in": ["Deságio", "Ad Valorem"], "efetivada": True},
        "operacao", True,
        "Tarifas de operacao (Aditivo Digital, Comunicados de Cessao, "
        "Consultas Financeiras, etc — retidas do liquido)",
        None,
    ),
    (
        "ad_valorem", "operacao", "AD_VALOREM", "OperacaoRentabilidade",
        {"descricao_eq": "Ad Valorem", "efetivada": True}, "operacao", True,
        "Ad valorem (factoring) retido do liquido",
        "Zero linhas em tenant sem ad valorem ativo — stream inofensivo.",
    ),
    # ── Tarifas de servico (conta grafica) ──────────────────────────────────
    (
        "tarifa_servico", "tarifa_servico", "TARIFA",
        "ContaCorrenteLancamento", {"codigos": _CODIGOS_TARIFA_SERVICO},
        "lancamento", False,
        "Tarifas de servico debitadas na conta grafica",
        "Ancoradas no vocabulario de wh_bitfin_tarifa_catalogo (Tipo 1).",
    ),
    # ── Repasse de custos (receita bruta com custo espelhado) ───────────────
    (
        "repasse_custo", "repasse_custo", "REPASSE_CUSTO",
        "ContaCorrenteLancamento",
        {"codigos": ["003", "015", "053", "088"]}, "lancamento", False,
        "Repasses de custo (carta de anuencia, custas de cartorio, custas "
        "processuais, circularizacao)",
        None,
    ),
    # ── Receita financeira de conta grafica ─────────────────────────────────
    (
        "financeira_correcao_diaria", "financeira", "FINANCEIRA",
        "ContaCorrenteLancamento",
        {"codigos": ["031"], "descricao_eq": "Correção Diária"},
        "lancamento", False,
        "Correcao diaria sobre saldo devedor de conta grafica (cod 031)",
        "GOTCHA: cod 031 e BIPOLAR — 'Rentabilidade de Debênture' (credito) "
        "e repasse a debenturista, NUNCA receita. O filtro descricao_eq e "
        "obrigatorio.",
    ),
]


def upgrade() -> None:
    # ── wh_bitfin_receita_stream (dim de streams) ───────────────────────────
    op.create_table(
        "wh_bitfin_receita_stream",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("stream_key", sa.String(length=50), nullable=False),
        sa.Column("familia", sa.String(length=30), nullable=False),
        sa.Column("natureza", sa.String(length=20), nullable=False),
        sa.Column("fonte_tabela", sa.String(length=50), nullable=False),
        sa.Column("criterio", JSONB(), nullable=False),
        sa.Column("grao", sa.String(length=20), nullable=False),
        sa.Column("retido_na_fonte", sa.Boolean(), nullable=False),
        sa.Column("descricao", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_wh_bitfin_receita_stream_tenant_id"),
        "wh_bitfin_receita_stream",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "uq_wh_bitfin_receita_stream_active",
        "wh_bitfin_receita_stream",
        ["tenant_id", "stream_key"],
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("valid_until IS NULL"),
    )

    # ── wh_receita_operacional (fato silver, Auditable) ─────────────────────
    op.create_table(
        "wh_receita_operacional",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("stream_key", sa.String(length=50), nullable=True),
        sa.Column("familia", sa.String(length=30), nullable=True),
        sa.Column("natureza", sa.String(length=20), nullable=True),
        sa.Column("valor", sa.Numeric(18, 2), nullable=False),
        sa.Column("titulo_id", sa.Integer(), nullable=True),
        sa.Column("operacao_id", sa.Integer(), nullable=True),
        sa.Column("recompra_id", sa.Integer(), nullable=True),
        sa.Column("lancamento_id", sa.Integer(), nullable=True),
        sa.Column("documento", sa.String(length=40), nullable=True),
        sa.Column("unidade_administrativa_id", sa.Integer(), nullable=True),
        sa.Column("produto_id", sa.Integer(), nullable=True),
        sa.Column("cedente_entidade_id", sa.Integer(), nullable=True),
        sa.Column("cedente_nome", sa.String(length=200), nullable=True),
        sa.Column("cedente_documento", sa.String(length=20), nullable=True),
        sa.Column("sacado_nome", sa.String(length=200), nullable=True),
        sa.Column("sacado_documento", sa.String(length=20), nullable=True),
        # Auditable (CLAUDE.md 14.1)
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("hash_origem", sa.String(length=64), nullable=True),
        sa.Column("ingested_by_version", sa.String(length=128), nullable=False),
        sa.Column("trust_level", sa.String(length=16), nullable=False),
        sa.Column("collected_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_receita_operacional_source"
        ),
    )
    for name, cols in [
        (op.f("ix_wh_receita_operacional_tenant_id"), ["tenant_id"]),
        (op.f("ix_wh_receita_operacional_data"), ["data"]),
        (op.f("ix_wh_receita_operacional_stream_key"), ["stream_key"]),
        (op.f("ix_wh_receita_operacional_natureza"), ["natureza"]),
        (op.f("ix_wh_receita_operacional_source_type"), ["source_type"]),
        (op.f("ix_wh_receita_operacional_source_id"), ["source_id"]),
        (
            op.f("ix_wh_receita_operacional_unidade_administrativa_id"),
            ["unidade_administrativa_id"],
        ),
        (
            op.f("ix_wh_receita_operacional_cedente_entidade_id"),
            ["cedente_entidade_id"],
        ),
        ("ix_wh_receita_operacional_tenant_comp", ["tenant_id", "competencia"]),
        (
            "ix_wh_receita_operacional_tenant_stream_comp",
            ["tenant_id", "stream_key", "competencia"],
        ),
        ("ix_wh_receita_operacional_tenant_titulo", ["tenant_id", "titulo_id"]),
    ]:
        op.create_index(name, "wh_receita_operacional", cols, unique=False)

    # ── seed dos 15 streams globais ─────────────────────────────────────────
    table = sa.table(
        "wh_bitfin_receita_stream",
        sa.column("id", sa.UUID()),
        sa.column("tenant_id", sa.UUID()),
        sa.column("version", sa.Integer()),
        sa.column("stream_key", sa.String()),
        sa.column("familia", sa.String()),
        sa.column("natureza", sa.String()),
        sa.column("fonte_tabela", sa.String()),
        sa.column("criterio", JSONB()),
        sa.column("grao", sa.String()),
        sa.column("retido_na_fonte", sa.Boolean()),
        sa.column("descricao", sa.String()),
        sa.column("notes", sa.Text()),
        sa.column("valid_from", sa.Date()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    from uuid import uuid4

    now = datetime.now(UTC)
    op.bulk_insert(
        table,
        [
            {
                "id": uuid4(),
                "tenant_id": None,
                "version": 1,
                "stream_key": key,
                "familia": familia,
                "natureza": natureza,
                "fonte_tabela": fonte,
                "criterio": criterio,
                "grao": grao,
                "retido_na_fonte": retido,
                "descricao": descricao,
                "notes": notes,
                "valid_from": _VALID_FROM,
                "created_at": now,
            }
            for key, familia, natureza, fonte, criterio, grao, retido, descricao, notes
            in _SEED
        ],
    )


def downgrade() -> None:
    op.drop_table("wh_receita_operacional")
    op.drop_table("wh_bitfin_receita_stream")
