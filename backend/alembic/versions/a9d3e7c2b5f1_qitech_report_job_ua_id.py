"""qitech_report_job: add unidade_administrativa_id + backfill raws orfaos

Bug descoberto em 2026-05-13: o fluxo assincrono `market.fidc_estoque`
gravava `wh_qitech_raw_relatorio` com `unidade_administrativa_id = NULL`
porque o `QitechReportJob` (intermediario entre POST e callback) nao tinha
a coluna. Coverage service filtra por UA -> os 23 raws SUCCESS ficavam
invisiveis pra UA RealInvest -> 58 furos visiveis no painel -> reconciler
re-enfileirava ad eternum. Loop interrompido pelo cap de tentativas (Fase
1.5), mas o sintoma visual nao se resolvia.

Fix:
1. Adicionar `unidade_administrativa_id` em `qitech_report_job` (nullable
   pra retrocompat — rows pre-fix continuam validas; o backfill abaixo
   preenche apos a migration).
2. Index pra acelerar lookup do reconciler ("ja existe job pendente pra
   essa UA+data?").
3. Backfill historico: setar `ua_id` nos jobs via match cnpj_fundo ->
   cadastros_unidade_administrativa.cnpj (mesmo tenant).
4. Propagar pros raws orfaos: UPDATE wh_qitech_raw_relatorio SET
   unidade_administrativa_id = job.ua_id WHERE ainda NULL E
   tipo_de_mercado = 'fidc-estoque'. Match preferencialmente via FK
   `raw_relatorio_id` no job; fallback via (tenant, data_posicao).

Pos-fix:
- Coverage service consegue ver os raws fidc-estoque do RealInvest -> os
  dias com SUCCESS deixam de aparecer como gap.
- Reconciler para de re-enfileirar datas ja sincronizadas.

Revision ID: a9d3e7c2b5f1
Revises: f2a8c7e1b9d3
Create Date: 2026-05-13 21:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9d3e7c2b5f1"
down_revision: str | None = "f2a8c7e1b9d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Schema — coluna + FK + index
    op.add_column(
        "qitech_report_job",
        sa.Column(
            "unidade_administrativa_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "cadastros_unidade_administrativa.id", ondelete="RESTRICT"
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_qitech_report_job_ua_type_date_status",
        "qitech_report_job",
        [
            "tenant_id",
            "unidade_administrativa_id",
            "report_type",
            "reference_date",
            "status",
        ],
    )

    # 2) Backfill: setar ua_id nos jobs via match cnpj_fundo
    #    (digits-only) <-> cadastros_unidade_administrativa.cnpj.
    #    Mesmo tenant. Quando nao houver UA correspondente, mantem NULL
    #    (rows muito antigas podem nao ter UA cadastrada hoje).
    op.execute(
        """
        UPDATE qitech_report_job j
        SET unidade_administrativa_id = ua.id
        FROM cadastros_unidade_administrativa ua
        WHERE j.unidade_administrativa_id IS NULL
          AND j.tenant_id = ua.tenant_id
          AND regexp_replace(COALESCE(ua.cnpj, ''), '\\D', '', 'g') = j.cnpj_fundo
        """
    )

    # 3) Propaga pros raws orfaos — match preferencial via FK do job,
    #    fallback via (tenant, tipo, data_posicao). Apenas fidc-estoque
    #    (familia que tem esse caminho assincrono).
    op.execute(
        """
        -- 3a. Match preferencial: job aponta FK pro raw
        UPDATE wh_qitech_raw_relatorio r
        SET unidade_administrativa_id = j.unidade_administrativa_id
        FROM qitech_report_job j
        WHERE r.id = j.raw_relatorio_id
          AND r.unidade_administrativa_id IS NULL
          AND j.unidade_administrativa_id IS NOT NULL
          AND r.tipo_de_mercado = 'fidc-estoque'
        """
    )
    op.execute(
        """
        -- 3b. Fallback: raws orfaos (sem FK no job) -> match por
        -- (tenant, data_posicao, tipo_de_mercado). Quando mais de 1 UA do
        -- mesmo tenant tem SUCCESS pra mesma data (raro), evitamos UPDATE
        -- ambiguo via DISTINCT + LATERAL pegando 1.
        UPDATE wh_qitech_raw_relatorio r
        SET unidade_administrativa_id = m.unidade_administrativa_id
        FROM (
            SELECT DISTINCT ON (j.tenant_id, j.reference_date)
                   j.tenant_id, j.reference_date, j.unidade_administrativa_id
            FROM qitech_report_job j
            WHERE j.report_type = 'fidc-estoque'
              AND j.status = 'SUCCESS'
              AND j.unidade_administrativa_id IS NOT NULL
            ORDER BY j.tenant_id, j.reference_date, j.completed_at DESC NULLS LAST
        ) m
        WHERE r.tenant_id = m.tenant_id
          AND r.data_posicao = m.reference_date
          AND r.tipo_de_mercado = 'fidc-estoque'
          AND r.unidade_administrativa_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_qitech_report_job_ua_type_date_status",
        table_name="qitech_report_job",
    )
    op.drop_column("qitech_report_job", "unidade_administrativa_id")
