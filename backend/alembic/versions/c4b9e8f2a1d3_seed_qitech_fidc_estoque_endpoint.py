"""seed_qitech_fidc_estoque_endpoint

Revision ID: c4b9e8f2a1d3
Revises: b7e2f3a8d4c9
Create Date: 2026-05-10 12:00:00.000000

Adiciona o endpoint `market.fidc_estoque` ao catalogo declarativo da QiTech.

Contexto: o relatorio FIDC Estoque (carteira de recebiveis cedidos) ja era
ingerido via fluxo assincrono (POST /v2/queue/scheduler/report/fidc-estoque
+ webhook callback em `routers/webhooks.py::process_fidc_estoque_callback`),
mas faltava entrada no `endpoint_catalog.py` — sem isso ele nao aparecia em
`/integracoes/catalogo/admin:qitech?tab=endpoints` e nao tinha registro de
proveniencia uniforme com os demais endpoints.

A migration original `d5bf3669b8a0_endpoint_scheduling.py` ja foi aplicada
em producao (flag flipped 2026-05-09), entao o snapshot inline daquela
migration permanece intocado. Esta migration estende o estado: para cada TSC
existente com `source_type='admin:qitech'`, popula 1 nova linha em TSEC
para o endpoint `market.fidc_estoque` com defaults `on_demand` / NULL.

ON_DEMAND e a escolha conservadora porque:
1. O fluxo e job + webhook (callback assincrono), nao polling sincrono — o
   scheduler que dispara DAILY_AT/INTERVAL espera retorno sincrono.
2. O handler em `adapter._HANDLERS` ainda nao esta wired (followup: criar
   handler que chame `request_fidc_estoque_report` e retorne step
   "job-enqueued"). Ate la, o webhook continua funcionando independente, mas
   "Sincronizar agora" pela UI levantara `RuntimeError(... sem handler ...)`.

Idempotente: usa `ON CONFLICT DO NOTHING` em cima do UQ
`uq_tenant_source_env_ua_endpoint`. Re-run da migration nao quebra.

**Bug historico (2026-05-09)**: a migration original de cadencia
(`d5bf3669b8a0_endpoint_scheduling.py`) usa `WHERE tsc.source_type = 'admin:qitech'`
(valor do enum). A coluna `tenant_source_config.source_type` na verdade
persiste o **nome** do enum em UPPER_SNAKE (`'ADMIN_QITECH'`), nao o value.
Resultado: aquela migration nao inseriu nada e a TSEC teve que ser
populada manualmente em prod. Esta migration usa `'ADMIN_QITECH'` direto
pra evitar repetir o bug. Ver memoria
`project_cadencia_endpoint_followups.md`.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4b9e8f2a1d3"
down_revision: str | None = "b7e2f3a8d4c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Snapshot inline (regra: migrations nao importam codigo de adapter).
# 1 endpoint adicionado ao catalogo QiTech.
NEW_ENDPOINT_NAME = "market.fidc_estoque"
NEW_ENDPOINT_KIND = "on_demand"
NEW_ENDPOINT_VALUE: str | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # Para cada TSC com admin:qitech, garante 1 linha em TSEC para o endpoint
    # novo. Se ja existir (re-run, ou criada por outro fluxo), no-op.
    bind.execute(
        sa.text(
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
                :schedule_kind,
                :schedule_value
            FROM tenant_source_config tsc
            WHERE tsc.source_type = 'ADMIN_QITECH'
            ON CONFLICT ON CONSTRAINT uq_tenant_source_env_ua_endpoint
                DO NOTHING
            """
        ),
        {
            "endpoint_name": NEW_ENDPOINT_NAME,
            "schedule_kind": NEW_ENDPOINT_KIND,
            "schedule_value": NEW_ENDPOINT_VALUE,
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM tenant_source_endpoint_config "
            "WHERE source_type = 'ADMIN_QITECH' "
            "AND endpoint_name = :endpoint_name"
        ),
        {"endpoint_name": NEW_ENDPOINT_NAME},
    )
