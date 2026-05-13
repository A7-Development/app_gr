"""scheduling: promote market.fidc_estoque de on_demand para daily_at 09:00

Info da QiTech recebida em 2026-05-13:
    "Para consultas do estoque de D-2 ou anterior nao ha um horario
    determinado. Para D-1 vai depender do horario de processamento do fundo
    (normalmente 8h-9h). O ideal e automatizar a partir das 09h, com retry
    apos as 10h caso nao retorne dados."

Decisao: schedule daily_at 09:00. O retry pos-10h fica coberto
implicitamente pelo reconciler (Fase 1 do auto-heal, services/reconciler.py)
— se o callback nao trouxe dado e D-1 segue como gap apos o tick das 09:30,
o reconciler enfileira novo BackfillJob (deduplicado contra QitechReportJob
pendente, em alteracao paralela).

Limpeza de duplicata: hoje a tabela tem 2 entries com (tenant, source_type,
endpoint_name)=(a7-credit, ADMIN_QITECH, market.fidc_estoque):
    - 1 com unidade_administrativa_id = NULL (criada 2026-05-11)
    - 1 com unidade_administrativa_id = 6170ce55... (RealInvest, 2026-05-10)
Como a UA principal ja tem entry propria, a row NULL fica como fallback
default que confunde — deletada nesta migration. Linhas com ua_id NULL
podem existir legitimamente quando o tenant nao escopa por UA, mas no caso
do fidc_estoque a granularidade e por UA (CNPJ do fundo). Manter apenas a
linha especifica.

Revision ID: f2a8c7e1b9d3
Revises: e4a7b2c9d031
Create Date: 2026-05-13 21:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a8c7e1b9d3"
down_revision: str | None = "e4a7b2c9d031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Promove TODAS as entries de fidc_estoque que estao on_demand pra
    #    daily_at 09:00. Idempotente — re-rodar nao afeta nada.
    op.execute(
        """
        UPDATE tenant_source_endpoint_config
        SET schedule_kind = 'daily_at',
            schedule_value = '09:00'
        WHERE endpoint_name = 'market.fidc_estoque'
          AND schedule_kind = 'on_demand'
        """
    )
    # 2) Remove as entries genericas (ua_id NULL) quando ja existe uma
    #    especifica pra mesma (tenant, source). A linha especifica vence;
    #    a generica vira ruido. Filtra so fidc_estoque pra nao mexer em
    #    outros endpoints onde NULL pode ser legitimo.
    op.execute(
        """
        DELETE FROM tenant_source_endpoint_config t
        WHERE t.endpoint_name = 'market.fidc_estoque'
          AND t.unidade_administrativa_id IS NULL
          AND EXISTS (
              SELECT 1 FROM tenant_source_endpoint_config s
              WHERE s.tenant_id = t.tenant_id
                AND s.source_type = t.source_type
                AND s.endpoint_name = t.endpoint_name
                AND s.unidade_administrativa_id IS NOT NULL
          )
        """
    )


def downgrade() -> None:
    # Reverte o schedule_kind. Nao recriamos a linha NULL apagada — se
    # alguem precisar reverter, recria via API (operacao de catalogo, nao
    # de schema).
    op.execute(
        """
        UPDATE tenant_source_endpoint_config
        SET schedule_kind = 'on_demand',
            schedule_value = NULL
        WHERE endpoint_name = 'market.fidc_estoque'
          AND schedule_kind = 'daily_at'
          AND schedule_value = '09:00'
        """
    )
