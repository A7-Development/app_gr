"""qitech silvers: troca UQ de (tenant_id, source_id) por business key

Revision ID: a4b7c9d2e8f1
Revises: d7e3a9b1f4c2
Create Date: 2026-05-19 14:00:00.000000

Fase C do refactor do bug v0.3.0 (commit 315241f) — separa o `source_id`
em proveniencia pura e introduz business keys explicitas como chave de
upsert nas 16 silvers QiTech. Tese: regra de geracao de `source_id` pode
mudar entre versoes do adapter sem quebrar idempotencia.

Cobertura desta migration:

  wh_mec_evolucao_cotas, wh_saldo_tesouraria, wh_posicao_cota_fundo,
  wh_saldo_conta_corrente, wh_posicao_outros_ativos, wh_posicao_renda_fixa,
  wh_posicao_compromissada, wh_rentabilidade_fundo, wh_cpr_movimento,
  wh_aquisicao_recebivel, wh_liquidacao_recebivel, wh_operacao_remessa,
  wh_estoque_recebivel, wh_movimento_aberto, wh_saldo_bancario_diario,
  wh_extrato_bancario.

Exclusao explicita: `wh_movimento_caixa`. QiTech publica lancamentos
byte-iguais legitimamente (ex.: 2 resgates do mesmo fundo no mesmo dia)
e a business key natural (descricao+valor+contas) tem 75 colisoes em
REALINVEST. Mantem (tenant_id, source_id) com sha16(item) ate refactor
com coluna `seq_no` discriminando lancamentos repetidos.

Padrao por tabela:

  1. Dedup defensivo: DELETE linhas duplicadas mantendo a mais recente
     por (ingested_at DESC, id DESC). Hash_origem identico = mesmo
     conteudo logico — dropar duplicata e seguro. Fase B (2026-05-19)
     mostrou 17 silvers limpas; este DELETE e idempotente.
  2. DROP CONSTRAINT uq_wh_*  (antiga, em tenant_id + source_id).
  3. CREATE UNIQUE CONSTRAINT uq_wh_* (nova, na business key).

A coluna `source_id` continua existindo nas tabelas (proveniencia —
"qual fetch trouxe esta linha"). Mantida NOT NULL pelo schema atual.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4b7c9d2e8f1"
down_revision: str | None = "d7e3a9b1f4c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (tabela, lista de colunas da business key)
SILVERS: list[tuple[str, list[str]]] = [
    ("wh_mec_evolucao_cotas", ["tenant_id", "data_posicao", "carteira_cliente_id"]),
    ("wh_saldo_tesouraria", ["tenant_id", "data_posicao", "carteira_cliente_id"]),
    ("wh_posicao_cota_fundo", ["tenant_id", "data_posicao", "carteira_cliente_id", "ativo_codigo"]),
    ("wh_saldo_conta_corrente", ["tenant_id", "data_posicao", "carteira_cliente_id", "codigo"]),
    ("wh_posicao_outros_ativos", ["tenant_id", "data_posicao", "carteira_cliente_id", "codigo"]),
    ("wh_posicao_renda_fixa", ["tenant_id", "data_posicao", "carteira_cliente_id", "codigo"]),
    ("wh_posicao_compromissada", ["tenant_id", "data_posicao", "carteira_cliente_id", "codigo"]),
    ("wh_rentabilidade_fundo", ["tenant_id", "data_posicao", "carteira_cliente_id", "indexador"]),
    ("wh_cpr_movimento", ["tenant_id", "data_posicao", "carteira_cliente_id", "descricao", "valor"]),
    ("wh_aquisicao_recebivel", ["tenant_id", "fundo_doc", "id_recebivel"]),
    ("wh_liquidacao_recebivel", ["tenant_id", "fundo_doc", "id_recebivel"]),
    ("wh_operacao_remessa", ["tenant_id", "fundo_doc", "id_operacao_recebivel"]),
    (
        "wh_estoque_recebivel",
        [
            "tenant_id", "data_referencia", "fundo_doc", "cedente_doc",
            "seu_numero", "numero_documento",
        ],
    ),
    (
        "wh_movimento_aberto",
        ["tenant_id", "data_referencia", "fundo_doc", "seu_numero", "numero_documento"],
    ),
    (
        "wh_saldo_bancario_diario",
        ["tenant_id", "unidade_administrativa_id", "agencia", "conta", "data_posicao"],
    ),
    (
        "wh_extrato_bancario",
        [
            "tenant_id", "unidade_administrativa_id", "agencia", "conta",
            "data_lancamento", "valor", "tipo", "descricao", "contrapartida_doc",
        ],
    ),
]


def _dedup_keep_newest_sql(table: str, bk: list[str]) -> str:
    """SQL para deletar duplicatas mantendo a linha mais recente por BK.

    Usa ROW_NUMBER OVER PARTITION BY (BK) ORDER BY ingested_at DESC, id DESC —
    O(n log n) com aggregate window function, evita o self-join O(n²) que
    trava em tabelas grandes (testado em wh_estoque_recebivel com 77k linhas:
    self-join >5min sem terminar, ROW_NUMBER termina em ~1s).

    Tupla `(ingested_at, id)` para desempate deterministico quando duas
    linhas tem o mesmo `ingested_at`.
    """
    bk_cols = ", ".join(bk)
    return f"""
        DELETE FROM {table}
        WHERE id IN (
          SELECT id FROM (
            SELECT id, ROW_NUMBER() OVER (
              PARTITION BY {bk_cols}
              ORDER BY ingested_at DESC, id DESC
            ) AS rn
            FROM {table}
          ) ranked
          WHERE rn > 1
        )
    """


def upgrade() -> None:
    for table, bk in SILVERS:
        # 1. Dedup defensivo: keep newest por BK
        op.execute(_dedup_keep_newest_sql(table, bk))

        # 2. DROP UQ antiga (tenant_id, source_id)
        # Convencao: nome da UQ = "uq_<table>"
        uq_name = f"uq_{table}"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {uq_name}")

        # 3. CREATE UQ nova na business key
        # NULLS NOT DISTINCT para que colunas opcionais (contrapartida_doc,
        # unidade_administrativa_id) deduplicem corretamente quando NULL.
        cols_sql = ", ".join(bk)
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {uq_name} "
            f"UNIQUE NULLS NOT DISTINCT ({cols_sql})"
        )


def downgrade() -> None:
    # Reverte cada silver: DROP UQ business key + recria UQ (tenant_id, source_id).
    # NAO recupera duplicatas que foram dedupadas no upgrade — perda
    # aceitavel (era duplicacao logica que ja deveria ter sido upserted).
    for table, _bk in SILVERS:
        uq_name = f"uq_{table}"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {uq_name}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {uq_name} "
            f"UNIQUE (tenant_id, source_id)"
        )
