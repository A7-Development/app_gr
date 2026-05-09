"""warehouse: tabelas QiTech ganham unidade_administrativa_id (multi-UA)

Revision ID: e7d1fa0c5b3a
Revises: c4f88a2e1e5b
Create Date: 2026-04-25 18:30:00.000000

Phase F warehouse — multi-UA QiTech (CLAUDE.md secao 13). Toda tabela
populada pelo adapter QiTech ganha `unidade_administrativa_id` para que dois
FIDCs do mesmo tenant nao se misturem no warehouse e a UI possa filtrar /
agrupar por UA sem string-matching de CNPJ.

Tabelas afetadas (15):
    Raw:
        wh_qitech_raw_relatorio
    Canonico (todas com UQ atual de (tenant_id, source_id)):
        wh_posicao_cota_fundo, wh_saldo_tesouraria, wh_saldo_conta_corrente,
        wh_movimento_caixa, wh_rentabilidade_fundo, wh_mec_evolucao_cotas,
        wh_cpr_movimento, wh_posicao_outros_ativos, wh_posicao_renda_fixa,
        wh_posicao_compromissada, wh_aquisicao_recebivel,
        wh_liquidacao_recebivel, wh_movimento_aberto, wh_operacao_remessa

Mudancas em cada tabela:
    1. ADD COLUMN unidade_administrativa_id UUID NULL.
    2. FK -> cadastros_unidade_administrativa(id) ON DELETE RESTRICT.
    3. Index ix_<tabela>_ua pra filter por UA.
    4. Backfill: para cada linha, vincula a 1a UA ativa do tenant
       (preferencia FIDC ativa mais antiga; mesma logica do tenant_source_config).
       Linhas de tenants sem UA cadastrada permanecem com NULL — aceitavel
       porque sao todos test fixtures (validado em 2026-04-25).

UQ na raw rotaciona pra incluir UA — duas UAs do mesmo tenant podem fetchar
o mesmo (tipo_de_mercado, data_posicao) em paralelo. UQs canonicas NAO
mudam: source_id ja e UA-scoped pela origem (cada UA tem seu portfolio
distinto na QiTech).

Downgrade: desfaz tudo (drop UQ nova da raw, restora UQ antiga, dropa
indices/FKs/colunas).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7d1fa0c5b3a"
down_revision: str | None = "c4f88a2e1e5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tabelas alvo. Ordem importa apenas para downgrade simetrico.
_TABLES: tuple[str, ...] = (
    "wh_qitech_raw_relatorio",
    "wh_posicao_cota_fundo",
    "wh_saldo_tesouraria",
    "wh_saldo_conta_corrente",
    "wh_movimento_caixa",
    "wh_rentabilidade_fundo",
    "wh_mec_evolucao_cotas",
    "wh_cpr_movimento",
    "wh_posicao_outros_ativos",
    "wh_posicao_renda_fixa",
    "wh_posicao_compromissada",
    "wh_aquisicao_recebivel",
    "wh_liquidacao_recebivel",
    "wh_movimento_aberto",
    "wh_operacao_remessa",
)


def _backfill_sql(table: str) -> str:
    """SQL pra backfillar UA do tenant na tabela informada.

    Mesma logica do tenant_source_config: 1a UA por tenant, ordenando por
    ativa DESC -> tipo='FIDC' DESC -> created_at ASC.
    """
    return f"""
        UPDATE {table} t
        SET unidade_administrativa_id = sub.ua_id
        FROM (
            SELECT DISTINCT ON (tenant_id)
                tenant_id,
                id AS ua_id
            FROM cadastros_unidade_administrativa
            ORDER BY
                tenant_id,
                ativa DESC,
                (tipo = 'FIDC') DESC,
                created_at ASC
        ) sub
        WHERE t.tenant_id = sub.tenant_id
          AND t.unidade_administrativa_id IS NULL
    """


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "unidade_administrativa_id",
                PG_UUID(as_uuid=True),
                nullable=True,
            ),
        )
        op.create_foreign_key(
            f"fk_{table}_ua",
            table,
            "cadastros_unidade_administrativa",
            ["unidade_administrativa_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(
            f"ix_{table}_ua",
            table,
            ["unidade_administrativa_id"],
        )
        op.execute(sa.text(_backfill_sql(table)))

    # Raw: rotate UQ pra incluir UA. PG trata NULLs como distintos por padrao,
    # entao linhas legacy (UA=NULL) nao bloqueiam upserts de novas linhas com
    # UA preenchida.
    op.drop_constraint(
        "uq_wh_qitech_raw_relatorio",
        "wh_qitech_raw_relatorio",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_wh_qitech_raw_relatorio",
        "wh_qitech_raw_relatorio",
        ["tenant_id", "tipo_de_mercado", "data_posicao", "unidade_administrativa_id"],
    )


def downgrade() -> None:
    # 1. Restaurar UQ antiga da raw
    op.drop_constraint(
        "uq_wh_qitech_raw_relatorio",
        "wh_qitech_raw_relatorio",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_wh_qitech_raw_relatorio",
        "wh_qitech_raw_relatorio",
        ["tenant_id", "tipo_de_mercado", "data_posicao"],
    )

    # 2. Drop coluna em ordem reversa pra simetria
    for table in reversed(_TABLES):
        op.drop_index(f"ix_{table}_ua", table_name=table)
        op.drop_constraint(f"fk_{table}_ua", table, type_="foreignkey")
        op.drop_column(table, "unidade_administrativa_id")
