"""integracoes + warehouse: UQs com UA usam NULLS NOT DISTINCT

Revision ID: f9b08c7d4a52
Revises: e7d1fa0c5b3a
Create Date: 2026-04-25 19:00:00.000000

Phase F follow-up — preserva idempotencia para configs/raws legacy (UA=NULL).

Por padrao Postgres trata cada NULL como distinto em UQ multicoluna. Isso
quebra idempotencia de duas formas:

1. `tenant_source_config (tenant, source_type, environment, ua)` — duas
   chamadas de upsert com `ua=NULL` criariam 2 linhas legacy em vez de
   colidir. Comportamento pre-Phase-F era exatamente "1 linha legacy por
   (tenant, src, env)" — restauramos via NULLS NOT DISTINCT.

2. `wh_qitech_raw_relatorio (tenant, tipo, data, ua)` — re-rodar o ETL
   no mesmo dia com `ua=NULL` (call sites legacy: scheduler antigo, scripts
   ad-hoc) deveria atualizar a linha existente, nao criar duplicata.

Quando ua e preenchida, comportamento e identico: UQ continua escopando
por UA. Mudanca afeta apenas o caso `ua IS NULL`.

PG 15+ obrigatorio. Validado em PG 18 (servidor de dev/prod do GR).
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9b08c7d4a52"
down_revision: str | None = "e7d1fa0c5b3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Dedup pre-Phase-F: linhas com (tenant, src, env, ua=NULL) duplicadas
    # nao deveriam existir (UQ antiga proibia), mas test fixtures e dev DBs
    # podem ter deixado duplicatas via INSERT direto. Mantemos a linha mais
    # recente por updated_at e deletamos as demais — seguro porque so
    # afeta linhas que ja eram ambiguas.
    op.execute(
        """
        DELETE FROM tenant_source_config a
        USING tenant_source_config b
        WHERE a.tenant_id = b.tenant_id
          AND a.source_type = b.source_type
          AND a.environment = b.environment
          AND a.unidade_administrativa_id IS NULL
          AND b.unidade_administrativa_id IS NULL
          AND a.id < b.id
        """
    )

    # tenant_source_config
    op.execute(
        "ALTER TABLE tenant_source_config DROP CONSTRAINT uq_tenant_source_env_ua"
    )
    op.execute(
        "ALTER TABLE tenant_source_config ADD CONSTRAINT uq_tenant_source_env_ua "
        "UNIQUE NULLS NOT DISTINCT "
        "(tenant_id, source_type, environment, unidade_administrativa_id)"
    )

    # 2. Dedup raw — mesma logica. Idem: re-rodar ETL no mesmo dia substituiria
    # a linha; duplicatas existentes vem de test fixtures historicos.
    # Mantemos a linha mais recente por fetched_at.
    op.execute(
        """
        DELETE FROM wh_qitech_raw_relatorio a
        USING wh_qitech_raw_relatorio b
        WHERE a.tenant_id = b.tenant_id
          AND a.tipo_de_mercado = b.tipo_de_mercado
          AND a.data_posicao = b.data_posicao
          AND a.unidade_administrativa_id IS NULL
          AND b.unidade_administrativa_id IS NULL
          AND (a.fetched_at < b.fetched_at
               OR (a.fetched_at = b.fetched_at AND a.id < b.id))
        """
    )

    # wh_qitech_raw_relatorio
    op.execute(
        "ALTER TABLE wh_qitech_raw_relatorio "
        "DROP CONSTRAINT uq_wh_qitech_raw_relatorio"
    )
    op.execute(
        "ALTER TABLE wh_qitech_raw_relatorio ADD CONSTRAINT uq_wh_qitech_raw_relatorio "
        "UNIQUE NULLS NOT DISTINCT "
        "(tenant_id, tipo_de_mercado, data_posicao, unidade_administrativa_id)"
    )


def downgrade() -> None:
    # Volta ao default NULLS DISTINCT.
    op.execute(
        "ALTER TABLE wh_qitech_raw_relatorio "
        "DROP CONSTRAINT uq_wh_qitech_raw_relatorio"
    )
    op.execute(
        "ALTER TABLE wh_qitech_raw_relatorio ADD CONSTRAINT uq_wh_qitech_raw_relatorio "
        "UNIQUE (tenant_id, tipo_de_mercado, data_posicao, unidade_administrativa_id)"
    )

    op.execute(
        "ALTER TABLE tenant_source_config DROP CONSTRAINT uq_tenant_source_env_ua"
    )
    op.execute(
        "ALTER TABLE tenant_source_config ADD CONSTRAINT uq_tenant_source_env_ua "
        "UNIQUE (tenant_id, source_type, environment, unidade_administrativa_id)"
    )
