"""Public contract of Integracoes module.

Outros modulos podem importar APENAS o que esta exposto aqui. Internals
(`models/`, `services/`, `adapters/`) sao proibidos de serem acessados de fora.

Consumidores atuais:
- `app/scheduler/sync_dispatcher.py` usa `list_due_configs`, `run_sync_one`
  e `rule_name_for` para disparar ciclos com base em `tenant_source_config`.
- `app/modules/integracoes/routers/sources.py` usa `run_sync_one` / `run_ping`
  para sync manual e teste de conexao.
- Outros modulos podem usar `is_source_enabled` para checar se uma fonte esta
  habilitada para um tenant (ex.: empty state no BI).
"""

from app.core.enums import SourceType
from app.modules.integracoes.adapters.admin.qitech.endpoint_catalog import (
    QITECH_ENDPOINTS,
)
from app.modules.integracoes.adapters.erp.bitfin.endpoint_catalog import (
    BITFIN_ENDPOINTS,
)
from app.modules.integracoes.services.eligibility import (
    is_source_enabled,
    list_enabled_configs,
)
from app.modules.integracoes.services.endpoint_scheduling import (
    list_due_endpoints,
    list_endpoint_configs_for_source,
)
from app.modules.integracoes.services.serasa_pj_query import (
    execute_pj_query as execute_serasa_pj_query,
)
from app.modules.integracoes.services.sync_runner import (
    rule_name_for,
    run_ping,
    run_sync_cycle,
    run_sync_endpoint,
    run_sync_one,
)
from app.shared.endpoint_catalog import EndpointSpec

# Source -> catalog. Sources without an entry (or with empty tuple) do not
# participate in per-endpoint scheduling — Serasa PJ/PF e SCR Bacen sao
# query-on-demand, nao sync periodico.
_CATALOG_BY_SOURCE: dict[SourceType, tuple[EndpointSpec, ...]] = {
    SourceType.ADMIN_QITECH: QITECH_ENDPOINTS,
    SourceType.ERP_BITFIN: BITFIN_ENDPOINTS,
    # Bureaus + document parsers nao tem catalogo (vazio implicito).
}


def endpoint_catalog(source_type: SourceType) -> list[EndpointSpec]:
    """Return the declarative endpoint catalog for a given source.

    Empty list = source does not participate in per-endpoint scheduling
    (e.g. bureaus que sao query sob demanda, parsers de documento, etc).

    The catalog is per-source, not per-tenant — endpoints are defined by the
    upstream API, identical for all tenants. Per-tenant overrides live in
    `tenant_source_endpoint_config` (DB).
    """
    return list(_CATALOG_BY_SOURCE.get(source_type, ()))


__all__ = [
    "endpoint_catalog",
    "execute_serasa_pj_query",
    "is_source_enabled",
    "list_due_endpoints",
    "list_enabled_configs",
    "list_endpoint_configs_for_source",
    "rule_name_for",
    "run_ping",
    "run_sync_cycle",
    "run_sync_endpoint",
    "run_sync_one",
]
