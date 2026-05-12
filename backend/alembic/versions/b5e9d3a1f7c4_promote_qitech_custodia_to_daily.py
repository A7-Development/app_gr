"""promote_qitech_custodia_to_daily

Revision ID: b5e9d3a1f7c4
Revises: a3c5d1e7b8f2
Create Date: 2026-05-12 19:00:00.000000

Promove os 4 endpoints `custodia.*` de `on_demand`/NULL para `daily_at`/HH:MM
no catalogo declarativo. Plano "Caminho 1" — cobertura continua dos relatorios
fidc-custodia, alinhado com a cadencia dos `market.*`.

Horarios escalonados (09:30 / 09:45 / 10:00 / 10:00) caem 1h depois dos
market.* (07:00-09:00) pra nao sobrecarregar o pool de conexao em pico unico.

Janelas resolvidas pelo handler quando dispatcher chama com `since=None`:
- custodia.aquisicao_consolidada: D-7..D-1 (janela rolante, captura
  correcoes tardias da QiTech via upsert idempotente por source_id).
- custodia.liquidados_baixados: D-7..D-1 idem.
- custodia.movimento_aberto: snapshot atual — gera serie temporal de
  cessoes em aberto ao longo do tempo.
- custodia.detalhes_operacoes: data alvo D-1.

Conservador: o UPDATE so toca linhas TSEC que ainda estao em estado
`on_demand` (default original do catalogo, antes da promocao). Se algum
tenant ja sobrescreveu manualmente para `interval`/outro `daily_at`,
preserva o intent dele. Logo, esta migration e segura para re-run e para
ambientes onde operadores tenham customizado defaults.

Idempotente: 2a execucao do UPDATE nao acha mais linhas `on_demand` para
esses endpoints e e no-op.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b5e9d3a1f7c4"
down_revision: str | None = "a3c5d1e7b8f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (endpoint_name, novo_schedule_value)
NEW_DEFAULTS: list[tuple[str, str]] = [
    ("custodia.aquisicao_consolidada", "09:30"),
    ("custodia.liquidados_baixados", "09:45"),
    ("custodia.movimento_aberto", "10:00"),
    ("custodia.detalhes_operacoes", "10:00"),
]


def upgrade() -> None:
    bind = op.get_bind()

    # UPDATE conservador: so toca linhas ainda em `on_demand` (estado default
    # antes da promocao). Override consciente do tenant (interval/outro
    # daily_at/...) e preservado.
    update_sql = sa.text(
        """
        UPDATE tenant_source_endpoint_config
        SET schedule_kind = 'daily_at',
            schedule_value = :new_value,
            updated_at = now()
        WHERE source_type = 'ADMIN_QITECH'
          AND endpoint_name = :endpoint_name
          AND schedule_kind = 'on_demand'
        """
    )

    for endpoint_name, new_value in NEW_DEFAULTS:
        bind.execute(
            update_sql,
            {"endpoint_name": endpoint_name, "new_value": new_value},
        )


def downgrade() -> None:
    bind = op.get_bind()

    # Reverte para `on_demand`/NULL — espelho do upgrade conservador.
    # So toca linhas que casam exatamente com o estado promovido (par
    # endpoint_name + valor que setamos no upgrade), preservando customizacoes
    # posteriores do tenant.
    downgrade_sql = sa.text(
        """
        UPDATE tenant_source_endpoint_config
        SET schedule_kind = 'on_demand',
            schedule_value = NULL,
            updated_at = now()
        WHERE source_type = 'ADMIN_QITECH'
          AND endpoint_name = :endpoint_name
          AND schedule_kind = 'daily_at'
          AND schedule_value = :promoted_value
        """
    )

    for endpoint_name, promoted_value in NEW_DEFAULTS:
        bind.execute(
            downgrade_sql,
            {
                "endpoint_name": endpoint_name,
                "promoted_value": promoted_value,
            },
        )
