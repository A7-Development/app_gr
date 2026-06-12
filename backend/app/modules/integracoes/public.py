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

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SourceType
from app.modules.integracoes.adapters.admin.qitech.endpoint_catalog import (
    QITECH_ENDPOINTS,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.liminar import (
    LIMINAR_RULE_VERSION as SERASA_LIMINAR_RULE_VERSION,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.liminar import (
    classify_negative_summary_message as classify_serasa_negative_summary_message,
)
from app.modules.integracoes.adapters.cobranca.etl import (
    run_cobranca_manual_sync,
)
from app.modules.integracoes.adapters.data.bigdatacorp.mappers.cadastral import (
    CadastralFields,
)
from app.modules.integracoes.adapters.erp.bitfin.endpoint_catalog import (
    BITFIN_ENDPOINTS,
)
from app.modules.integracoes.report_catalog import (
    REPORTS,
    REPORTS_BY_SLUG,
    ReportCategory,
    ReportSpec,
)
from app.modules.integracoes.services.bdc_cadastral_query import (
    CadastralQueryResult,
    fetch_cadastral_pj,
)
from app.modules.integracoes.services.dia_util import (
    dia_util_anterior_qitech,
)
from app.modules.integracoes.services.dia_util import (
    listar_datas_disponiveis as listar_datas_disponiveis_qitech,
)
from app.modules.integracoes.services.eligibility import (
    is_source_enabled,
    list_enabled_configs,
)
from app.modules.integracoes.services.endpoint_scheduling import (
    list_due_endpoints,
    list_endpoint_configs_for_source,
)
from app.modules.integracoes.services.infosimples_junta import (
    JuntaDownloadResult,
    JuntaFichaResult,
    JuntaListaDocsResult,
    fetch_junta_documento,
    fetch_junta_ficha,
    fetch_junta_lista_documentos,
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

# Sources that participate in the report catalog. When a new admin (Kanastra,
# BTG, ...) is integrated, add the SourceType here so its reports are
# considered when filtering by tenant subscription.
_ADMIN_SOURCES_IN_REPORT_CATALOG: tuple[SourceType, ...] = (
    SourceType.ADMIN_QITECH,
)

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


async def list_reports(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    category: ReportCategory | None = None,
) -> list[ReportSpec]:
    """Return reports from the catalog visible to a tenant.

    Visibility = the report's `administradora` has `tenant_source_config.enabled=true`
    for this tenant (production environment). Tenants that have not connected
    QiTech do not see QiTech reports.

    Owned by integracoes (the catalog data is sourced from adapters); consumed
    by `controladoria.api.reports` to render the catalog page.
    """
    enabled_admins: set[SourceType] = set()
    for admin_source in _ADMIN_SOURCES_IN_REPORT_CATALOG:
        if await is_source_enabled(db, tenant_id, admin_source):
            enabled_admins.add(admin_source)

    visible = [r for r in REPORTS if r.administradora in enabled_admins]
    if category is not None:
        visible = [r for r in visible if r.category == category]
    return visible


def get_report_spec(slug: str) -> ReportSpec | None:
    """O(1) lookup of a report spec by slug. Returns None if slug unknown."""
    return REPORTS_BY_SLUG.get(slug)


__all__ = [
    "SERASA_LIMINAR_RULE_VERSION",
    "CadastralFields",
    "CadastralQueryResult",
    "JuntaDownloadResult",
    "JuntaFichaResult",
    "JuntaListaDocsResult",
    "ReportCategory",
    "ReportSpec",
    "classify_serasa_negative_summary_message",
    "dia_util_anterior_qitech",
    "endpoint_catalog",
    "execute_serasa_pj_query",
    "fetch_cadastral_pj",
    "fetch_junta_documento",
    "fetch_junta_ficha",
    "fetch_junta_lista_documentos",
    "get_report_spec",
    "is_source_enabled",
    "list_due_endpoints",
    "list_enabled_configs",
    "list_endpoint_configs_for_source",
    "list_reports",
    "listar_datas_disponiveis_qitech",
    "rule_name_for",
    "run_cobranca_manual_sync",
    "run_ping",
    "run_sync_cycle",
    "run_sync_endpoint",
    "run_sync_one",
]
