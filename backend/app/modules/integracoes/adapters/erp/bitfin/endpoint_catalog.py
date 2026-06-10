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
        admin_code="bitfin",
        name="bitfin.full_sync",
        label="Bitfin · Sync completo",
        description=(
            "Carrega Operacoes, Titulos, DRE e dimensoes do banco SQL Server "
            "do Bitfin para o warehouse silver. Nao tem granularidade por "
            "tabela — sync atomico por tenant."
        ),
        default_schedule_kind=ScheduleKind.INTERVAL,
        default_schedule_value="30",
        canonical_table="wh_titulo, wh_operacao, wh_dre, wh_caixa_snapshot",
    ),
    # Relay Serasa (2026-05-26): replica as consultas Serasa Relato PJ feitas
    # DENTRO do Bitfin (dbo.ConsultaFinanceira.Relatorio, gzip JSON) para o
    # warehouse wh_serasa_pj_*, reusando o mapper Serasa do GR. Incremental
    # por watermark de ConsultaFinanceiraId (idempotente). Endpoint proprio
    # (schedule/enable independentes do full_sync do ERP).
    # Party model (2026-06-10): Entidade completa + papeis (Cliente/Sacado) +
    # grupo economico -> wh_entidade / wh_entidade_fonte / wh_entidade_papel /
    # wh_grupo_economico(_membro). Fundacao da identidade canonica (F0) —
    # cadencia propria (cadastro muda devagar; 6h e folgado).
    EndpointSpec(
        admin_code="bitfin",
        name="bitfin.entidades",
        label="Bitfin · Entidades (party model)",
        description=(
            "Carrega o cadastro completo de entidades (CNPJ/CPF), papeis "
<<<<<<< HEAD
            "(cedente/sacado), grupos economicos e posicoes por papel "
            "(risco/limites/liquidez) para o warehouse canonico. "
            "Full refresh idempotente."
        ),
        default_schedule_kind=ScheduleKind.INTERVAL,
        default_schedule_value="360",
        canonical_table="wh_entidade, wh_entidade_papel, wh_posicao_cedente, wh_posicao_sacado",
=======
            "(cedente/sacado) e grupos economicos para o warehouse canonico "
            "wh_entidade. Full refresh idempotente."
        ),
        default_schedule_kind=ScheduleKind.INTERVAL,
        default_schedule_value="360",
        canonical_table="wh_entidade, wh_entidade_papel, wh_grupo_economico",
>>>>>>> origin/main
    ),
    EndpointSpec(
        admin_code="bitfin",
        name="bitfin.serasa_relay",
        label="Bitfin · Relay Serasa PJ",
        description=(
            "Replica as consultas Serasa (Relato PJ Analitico) registradas no "
            "Bitfin para o warehouse wh_serasa_pj_*. Incremental por "
            "ConsultaFinanceiraId; nao faz chamada paga a Serasa."
        ),
        default_schedule_kind=ScheduleKind.INTERVAL,
        default_schedule_value="15",
        canonical_table="wh_serasa_pj_consulta",
    ),
)


BITFIN_ENDPOINTS_BY_NAME: dict[str, EndpointSpec] = {
    ep.name: ep for ep in BITFIN_ENDPOINTS
}
