"""qitech silvers: adiciona FK raw_id para replace-by-partition

Revision ID: c8a3d2b1f7e9
Revises: b4f1a8d2c903
Create Date: 2026-05-20 11:30:00.000000

Fase 1.1 do refactor "espelho fiel da QiTech" (decisao 2026-05-20).

Tese: o silver eh projecao do raw, nao acumulador. Hoje o write eh UPSERT
puro por business key — registros que SUMIRAM do payload em re-sync ficam
orfaos no silver (caso classico de QiTech corrigindo retroativamente e
removendo titulos). Esta migration prepara o terreno pra trocar UPSERT por
DELETE-and-INSERT atomico no scope do raw payload — caminho codigo na
Fase 1.3 (_replace_canonical_partition).

Mudanca de schema: cada uma das 16 silvers QiTech ganha coluna `raw_id`
(FK pra a raw correspondente, ON DELETE CASCADE). Nullable inicial pra
permitir backfill assincrono em Fase 1.6 — rows com raw_id=NULL ficam no
caminho UPSERT legado ate o backfill terminar.

QiTech tem 3 raws distintos; FK aponta pro raw correto por silver:

  wh_qitech_raw_relatorio (14 silvers — "market" + "custodia"):
    wh_posicao_cota_fundo, wh_saldo_conta_corrente, wh_saldo_tesouraria,
    wh_posicao_outros_ativos, wh_cpr_movimento, wh_mec_evolucao_cotas,
    wh_rentabilidade_fundo, wh_posicao_renda_fixa, wh_posicao_compromissada,
    wh_aquisicao_recebivel, wh_liquidacao_recebivel, wh_estoque_recebivel,
    wh_movimento_aberto, wh_operacao_remessa

  wh_qitech_raw_bank_account_balance (1 silver):
    wh_saldo_bancario_diario

  wh_qitech_raw_bank_account_statement (1 silver):
    wh_extrato_bancario

ON DELETE CASCADE eh deliberado: silver eh projecao do raw — se raw eh
apagado (housekeeping, retencao), as silver linhas projetadas dele devem
ir junto. Reaparecer o raw repopula silver via ETL.

Exclusao explicita: wh_movimento_caixa. Tem business key fragil (75 dups
legitimas REALINVEST 14/05/2026, ver [[project_qitech_business_key_uq]]).
Continua no caminho UPSERT-by-source_id ate refactor com `seq_no`.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c8a3d2b1f7e9"
down_revision: str | None = "b4f1a8d2c903"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (silver_table, raw_table) — raw_table eh a tabela apontada pela FK raw_id.
SILVERS_TO_RAW: list[tuple[str, str]] = [
    # wh_qitech_raw_relatorio
    ("wh_posicao_cota_fundo",     "wh_qitech_raw_relatorio"),
    ("wh_saldo_conta_corrente",   "wh_qitech_raw_relatorio"),
    ("wh_saldo_tesouraria",       "wh_qitech_raw_relatorio"),
    ("wh_posicao_outros_ativos",  "wh_qitech_raw_relatorio"),
    ("wh_cpr_movimento",          "wh_qitech_raw_relatorio"),
    ("wh_mec_evolucao_cotas",     "wh_qitech_raw_relatorio"),
    ("wh_rentabilidade_fundo",    "wh_qitech_raw_relatorio"),
    ("wh_posicao_renda_fixa",     "wh_qitech_raw_relatorio"),
    ("wh_posicao_compromissada",  "wh_qitech_raw_relatorio"),
    ("wh_aquisicao_recebivel",    "wh_qitech_raw_relatorio"),
    ("wh_liquidacao_recebivel",   "wh_qitech_raw_relatorio"),
    ("wh_estoque_recebivel",      "wh_qitech_raw_relatorio"),
    ("wh_movimento_aberto",       "wh_qitech_raw_relatorio"),
    ("wh_operacao_remessa",       "wh_qitech_raw_relatorio"),
    # wh_qitech_raw_bank_account_*
    ("wh_saldo_bancario_diario",  "wh_qitech_raw_bank_account_balance"),
    ("wh_extrato_bancario",       "wh_qitech_raw_bank_account_statement"),
]


def _fk_name(silver: str, raw: str) -> str:
    # Convencao curta — Postgres limita identificadores a 63 chars.
    # "fk_<silver_sem_wh>_raw_id" cabe em todos os casos.
    return f"fk_{silver.removeprefix('wh_')}_raw_id"


def _ix_name(silver: str) -> str:
    return f"ix_{silver.removeprefix('wh_')}_raw_id"


def upgrade() -> None:
    for silver, raw in SILVERS_TO_RAW:
        # 1. Coluna nullable (backfill em Fase 1.6 popula retroativamente).
        op.add_column(
            silver,
            sa.Column("raw_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        # 2. FK com ON DELETE CASCADE.
        op.create_foreign_key(
            _fk_name(silver, raw),
            silver,
            raw,
            ["raw_id"],
            ["id"],
            ondelete="CASCADE",
        )
        # 3. Indice em raw_id — DELETE/SELECT por raw_id eh o hot path
        #    do _replace_canonical_partition.
        op.create_index(_ix_name(silver), silver, ["raw_id"])


def downgrade() -> None:
    for silver, raw in reversed(SILVERS_TO_RAW):
        op.drop_index(_ix_name(silver), table_name=silver)
        op.drop_constraint(_fk_name(silver, raw), silver, type_="foreignkey")
        op.drop_column(silver, "raw_id")
