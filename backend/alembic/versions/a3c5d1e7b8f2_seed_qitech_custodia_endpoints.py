"""seed_qitech_custodia_endpoints

Revision ID: a3c5d1e7b8f2
Revises: d2a8e4f1b3c7
Create Date: 2026-05-12 18:00:00.000000

Adiciona 4 endpoints `custodia.*` ao catalogo declarativo da QiTech.

Contexto: a familia `/v2/fidc-custodia/report/*` ja era invocavel via REST
proprio (`POST /integracoes/qitech/custodia/<name>/sync` em
`routers/qitech_custodia.py`), mas faltava entrada no `endpoint_catalog.py`
— sem isso esses endpoints nao apareciam em
`/integracoes/catalogo/admin:qitech?tab=endpoints` e ficavam invisiveis na
visao "controle do que estamos consumindo".

Apos esta migration:
- 17 endpoints no catalogo QiTech (10 market + 1 fidc_estoque async + 4
  custodia + 2 bank_account).
- Os 4 custodia.* sao ON_DEMAND — nao entram no scheduler do dispatcher.
- Botao "Sincronizar agora" funciona via handlers em
  `adapters/admin/qitech/adapter.py::_HANDLERS` que resolvem UA -> CNPJ e
  chamam funcoes em `custodia.py` com defaults (D-7..D-1 / D-1 / snapshot).
- Backfill com janela arbitraria continua disponivel via REST proprio.

Idempotente: usa `ON CONFLICT DO NOTHING` em cima do UQ
`uq_tenant_source_env_ua_endpoint`. Re-run da migration nao quebra.

Snapshot inline (regra CLAUDE.md: migrations nao importam codigo de adapter
— este pattern foi tomado da migration `c4b9e8f2a1d3`).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3c5d1e7b8f2"
down_revision: str | None = "d2a8e4f1b3c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 4 endpoints adicionados ao catalogo QiTech (todos ON_DEMAND).
NEW_ENDPOINTS: list[str] = [
    "custodia.aquisicao_consolidada",
    "custodia.liquidados_baixados",
    "custodia.movimento_aberto",
    "custodia.detalhes_operacoes",
]


def upgrade() -> None:
    bind = op.get_bind()

    # Para cada TSC com admin:qitech, garante 1 linha em TSEC por endpoint
    # novo. Se ja existir (re-run, ou criada por outro fluxo), no-op.
    #
    # Nota: a coluna `tenant_source_config.source_type` persiste o NOME do
    # enum em UPPER_SNAKE (`ADMIN_QITECH`), nao o value (`admin:qitech`).
    # Ver memoria `project_cadencia_endpoint_followups.md` para historia.
    insert_sql = sa.text(
        """
        INSERT INTO tenant_source_endpoint_config
            (id, tenant_id, source_type, environment,
             unidade_administrativa_id, endpoint_name, enabled,
             schedule_kind, schedule_value)
        SELECT
            gen_random_uuid(),
            tsc.tenant_id,
            tsc.source_type,
            tsc.environment,
            tsc.unidade_administrativa_id,
            :endpoint_name,
            tsc.enabled,
            'on_demand',
            NULL
        FROM tenant_source_config tsc
        WHERE tsc.source_type = 'ADMIN_QITECH'
        ON CONFLICT ON CONSTRAINT uq_tenant_source_env_ua_endpoint
            DO NOTHING
        """
    )

    for name in NEW_ENDPOINTS:
        bind.execute(insert_sql, {"endpoint_name": name})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM tenant_source_endpoint_config "
            "WHERE source_type = 'ADMIN_QITECH' "
            "AND endpoint_name = ANY(:names)"
        ),
        {"names": NEW_ENDPOINTS},
    )
