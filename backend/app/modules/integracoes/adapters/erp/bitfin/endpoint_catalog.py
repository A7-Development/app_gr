"""Bitfin adapter — declarative endpoint catalog.

Bitfin is a SQL Server ERP read by `etl.py::sync_all` as a single monolithic
sync (Operacao + Titulo + DRE + dimensoes). It does not expose multiple HTTP
endpoints like QiTech does — there is exactly **one** logical endpoint:
"sync everything from Bitfin for this tenant".

Catalog has 1 entry — `bitfin.full_sync` — for **uniformity** with QiTech.
This means:
    - The dispatcher iterates `tenant_source_endpoint_config` only (one
      code path), not per-source-special-case Bitfin.
    - The frontend `EndpointsTab` shows Bitfin with 1 row; no special UI.
    - When/if Bitfin becomes multi-endpoint (e.g. split Operacao from
      Titulo), we add entries here without touching the dispatcher.

Default cadence: 30 min, matching the legacy hardcoded value in
`scheduler/jobs/bitfin_sync.py` (deleted by the dispatcher refactor in
PR2 of this initiative).

NOTE: Keep in sync with BITFIN_SNAPSHOT inside the Alembic migration that
seeds `tenant_source_endpoint_config` — see CLAUDE.md migration rules.
"""

from __future__ import annotations

from app.shared.endpoint_catalog import EndpointSpec, ScheduleKind

BITFIN_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        name="bitfin.full_sync",
        label="Bitfin · Sync completo",
        description=(
            "Carrega Operacoes, Titulos, DRE e dimensoes do banco SQL Server "
            "do Bitfin para o warehouse silver. Nao tem granularidade por "
            "tabela — sync atomico por tenant."
        ),
        default_schedule_kind=ScheduleKind.INTERVAL,
        default_schedule_value="30",
        canonical_table="wh_titulo, wh_operacao, wh_dre",
    ),
)


BITFIN_ENDPOINTS_BY_NAME: dict[str, EndpointSpec] = {
    ep.name: ep for ep in BITFIN_ENDPOINTS
}
