"""QiTech adapter — declarative endpoint catalog.

13 endpoints today (2026-05-10):
    - 10 market reports sincronos (`etl.py::_PIPELINE`, soon to be deleted)
    - 1 market report assincrono (`fidc_estoque` via job + webhook em
      `report_jobs.py`; ver `routers/webhooks.py::process_fidc_estoque_callback`)
    - 2 bank-account reports (`bank_account_sync.py`)

Defaults follow the rough operational pattern of QiTech / Singulare:
    * Market reports for D-1 are published from ~3am-6am SP. We sync mid-morning
      to give margin while still surfacing fresh data before traders log in.
    * `bank_account.balance` is end-of-day — sync after 18h SP.
    * `bank_account.statement` (transactions) — hourly, since intraday lançamentos
      arrive throughout the day.

Defaults exist so that a freshly-onboarded tenant has sensible cadences without
having to set every endpoint by hand. Tenants that care can override per
endpoint via `/integracoes/catalogo/admin:qitech?tab=endpoints`.

NOTE: The schedule_kind/value defaults here MUST be kept in sync with the
QITECH_SNAPSHOT in `alembic/versions/<rev>_endpoint_scheduling.py`. The
migration intentionally hardcodes a snapshot inline (per CLAUDE.md migration
rule: migrations must not import code from adapters). Keeping them in sync
is a manual contract — the test
`tests/modules/integracoes/test_endpoint_catalog.py::test_catalog_matches_migration_snapshot`
guards regression.
"""

from __future__ import annotations

from app.shared.endpoint_catalog import EndpointSpec, ScheduleKind

# ─────────────────────────────────────────────────────────────────────────────
# Market reports — ETL canonical pipeline
# ─────────────────────────────────────────────────────────────────────────────

_MARKET_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        name="market.outros_fundos",
        label="Mercado · Outros fundos",
        description="Posicao em outros fundos do FIDC (PL, cota) — relatorio D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="07:00",
        canonical_table="wh_posicao_cota_fundo",
    ),
    EndpointSpec(
        name="market.conta_corrente",
        label="Mercado · Conta-corrente",
        description="Saldo de conta-corrente do FIDC — relatorio D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="07:30",
        canonical_table="wh_saldo_conta_corrente",
    ),
    EndpointSpec(
        name="market.tesouraria",
        label="Mercado · Tesouraria",
        description="Posicao de tesouraria do FIDC — relatorio D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="07:30",
        canonical_table="wh_saldo_tesouraria",
    ),
    EndpointSpec(
        name="market.outros_ativos",
        label="Mercado · Outros ativos",
        description="Posicoes diversas nao classificadas em renda fixa/variavel.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:00",
        canonical_table="wh_posicao_outros_ativos",
    ),
    EndpointSpec(
        name="market.demonstrativo_caixa",
        label="Mercado · Demonstrativo de caixa",
        description="Movimentacao de caixa do FIDC — entradas/saidas D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:00",
        canonical_table="wh_movimento_caixa",
    ),
    EndpointSpec(
        name="market.cpr",
        label="Mercado · CPR",
        description="Contas a pagar e receber — movimento D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:30",
        canonical_table="wh_cpr_movimento",
    ),
    EndpointSpec(
        name="market.mec",
        label="Mercado · MEC (mapa evolutivo de cotas)",
        description="Evolucao de cotas do FIDC — relatorio D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:30",
        canonical_table="wh_mec_evolucao_cotas",
    ),
    EndpointSpec(
        name="market.rentabilidade",
        label="Mercado · Rentabilidade",
        description="Rentabilidade calculada do FIDC.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="09:00",
        canonical_table="wh_rentabilidade_fundo",
    ),
    EndpointSpec(
        name="market.rf",
        label="Mercado · Renda fixa",
        description="Posicoes de renda fixa do FIDC — D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:00",
        canonical_table="wh_posicao_renda_fixa",
    ),
    EndpointSpec(
        name="market.rf_compromissadas",
        label="Mercado · Compromissadas",
        description="Posicoes em operacoes compromissadas — D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:00",
        canonical_table="wh_posicao_compromissada",
    ),
    # Estoque do FIDC (carteira de recebiveis cedidos) — fluxo assincrono via
    # job + webhook callback. POST /v2/queue/scheduler/report/fidc-estoque
    # devolve jobId; QiTech processa e chama nosso /webhooks/qitech/job-callback.
    # Ver `report_jobs.py::request_fidc_estoque_report` +
    # `process_fidc_estoque_callback`. Default ON_DEMAND porque o disparo nao
    # cabe no scheduler de polling — handler em adapter._HANDLERS pendente.
    EndpointSpec(
        name="market.fidc_estoque",
        label="Mercado · Estoque do FIDC (carteira)",
        description="Posicao consolidada da carteira de recebiveis do FIDC. Disparo assincrono via job + webhook callback.",
        default_schedule_kind=ScheduleKind.ON_DEMAND,
        default_schedule_value=None,
        canonical_table="wh_estoque_recebivel",
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# Bank-account endpoints (separados do _PIPELINE no etl.py — vivem em
# `bank_account_sync.py`).
# ─────────────────────────────────────────────────────────────────────────────

_BANK_ACCOUNT_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        name="bank_account.balance",
        label="Conta-corrente · Saldo",
        description="Saldo de fechamento das contas-corrente Singulare. Disponivel apos ~18h SP.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="19:00",
        canonical_table="wh_bank_account_balance",
    ),
    EndpointSpec(
        name="bank_account.statement",
        label="Conta-corrente · Extrato",
        description="Lancamentos da conta-corrente — atualizados ao longo do dia.",
        default_schedule_kind=ScheduleKind.INTERVAL,
        default_schedule_value="60",
        canonical_table="wh_bank_account_statement",
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Public catalog
# ─────────────────────────────────────────────────────────────────────────────

QITECH_ENDPOINTS: tuple[EndpointSpec, ...] = (
    *_MARKET_ENDPOINTS,
    *_BANK_ACCOUNT_ENDPOINTS,
)


# Index for O(1) lookup by name — used by handlers/dispatch.
QITECH_ENDPOINTS_BY_NAME: dict[str, EndpointSpec] = {
    ep.name: ep for ep in QITECH_ENDPOINTS
}
