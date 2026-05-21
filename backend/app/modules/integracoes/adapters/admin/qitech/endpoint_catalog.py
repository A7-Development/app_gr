"""QiTech adapter — declarative endpoint catalog.

17 endpoints today (2026-05-12):
    - 10 market reports sincronos (`etl.py::_PIPELINE`, soon to be deleted)
    - 1 market report assincrono (`fidc_estoque` via job + webhook em
      `report_jobs.py`; ver `routers/webhooks.py::process_fidc_estoque_callback`)
    - 2 bank-account reports (`bank_account_sync.py`)
    - 4 custodia reports on-demand (`custodia.py` — familia
      /v2/fidc-custodia/report/*: aquisicao_consolidada, liquidados_baixados,
      movimento_aberto, detalhes_operacoes). Disparados via REST proprio
      (`qitech_custodia.py`) E via endpoints genericos
      (`/sources/{src}/endpoints/{name}/sync`) — handlers em `adapter._HANDLERS`.

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

# Prefix relpath dos arquivos .md de payload shape (Fase 2 do refactor de
# proveniencia transversal, 2026-05-18). Convencao: 1 arquivo por endpoint
# em `payload_shapes/<name>.md`. Consumido pela UI admin pra abrir doc
# in-line do shape do payload.
_PAYLOAD_SHAPE_DIR = (
    "backend/app/modules/integracoes/adapters/admin/qitech/payload_shapes"
)


def _shape(name: str) -> str:
    """Relpath canonico do .md pra um endpoint QiTech."""
    return f"{_PAYLOAD_SHAPE_DIR}/{name}.md"

# ─────────────────────────────────────────────────────────────────────────────
# Market reports — ETL canonical pipeline
# ─────────────────────────────────────────────────────────────────────────────

#
# Defaults de tolerancia para market reports QiTech (2026-05-15):
#
#   expected=1, tolerance=3, give_up=10
#
# Reflete o que observamos em producao: market reports de D-1 sao publicados
# ate ~D+1 09:30 SP na maioria dos dias. D+2 ja e atrasado (operador deve
# notar); D+3..D+9 e suspeito (problema na fonte); D+10 e abandono (raro mas
# acontece — ex.: 30/04 furou e so apareceu semanas depois).
#
# Mexer por endpoint quando houver evidencia empirica (ex.: rentabilidade
# que historicamente vem mais tarde, ou rf_compromissadas que tem cadencia
# irregular). Por enquanto manter uniforme.
#
_MARKET_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        admin_code="qitech",
        name="market.outros_fundos",
        label="Mercado · Outros fundos",
        description="Posicao em outros fundos do FIDC (PL, cota) — relatorio D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="07:00",
        canonical_table="wh_posicao_cota_fundo",
        payload_shape_doc_relpath=_shape("market.outros_fundos"),
        # F3, 2026-05-21 — ligado junto com os demais market.* sincronos
        # apos validacao do piloto em market.conta_corrente.
        state_machine_enabled=True,
    ),
    EndpointSpec(
        admin_code="qitech",
        name="market.conta_corrente",
        label="Mercado · Conta-corrente",
        description="Saldo de conta-corrente do FIDC — relatorio D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="07:30",
        canonical_table="wh_saldo_conta_corrente",
        payload_shape_doc_relpath=_shape("market.conta_corrente"),
        # PILOTO da state machine (F1.5, 2026-05-19). Selecionado por:
        # 1) Alto volume — toda data util tem dado, exercita todas transicoes.
        # 2) Foi um dos 5 endpoints presos em 2026-05-15 pro REALINVEST —
        #    state machine valida no caso real que motivou o refactor.
        # 3) Sem downstream critico (Cota Sub depende de CPR/MEC/FIDC estoque,
        #    nao deste) — rollback nao impacta dashboards principais.
        # Demais endpoints continuam no caminho legado ate validacao.
        state_machine_enabled=True,
    ),
    EndpointSpec(
        admin_code="qitech",
        name="market.tesouraria",
        label="Mercado · Tesouraria",
        description="Posicao de tesouraria do FIDC — relatorio D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="07:30",
        canonical_table="wh_saldo_tesouraria",
        payload_shape_doc_relpath=_shape("market.tesouraria"),
        state_machine_enabled=True,  # F3, 2026-05-21
    ),
    EndpointSpec(
        admin_code="qitech",
        name="market.outros_ativos",
        label="Mercado · Outros ativos",
        description="Posicoes diversas nao classificadas em renda fixa/variavel.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:00",
        canonical_table="wh_posicao_outros_ativos",
        payload_shape_doc_relpath=_shape("market.outros_ativos"),
        state_machine_enabled=True,  # F3, 2026-05-21
    ),
    EndpointSpec(
        admin_code="qitech",
        name="market.demonstrativo_caixa",
        label="Mercado · Demonstrativo de caixa",
        description="Movimentacao de caixa do FIDC — entradas/saidas D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:00",
        canonical_table="wh_movimento_caixa",
        payload_shape_doc_relpath=_shape("market.demonstrativo_caixa"),
        state_machine_enabled=True,  # F3, 2026-05-21
    ),
    EndpointSpec(
        admin_code="qitech",
        name="market.cpr",
        label="Mercado · CPR",
        description="Contas a pagar e receber — movimento D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:30",
        canonical_table="wh_cpr_movimento",
        payload_shape_doc_relpath=_shape("market.cpr"),
        state_machine_enabled=True,  # F3, 2026-05-21
    ),
    EndpointSpec(
        admin_code="qitech",
        name="market.mec",
        label="Mercado · MEC (mapa evolutivo de cotas)",
        description="Evolucao de cotas do FIDC — relatorio D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:30",
        canonical_table="wh_mec_evolucao_cotas",
        payload_shape_doc_relpath=_shape("market.mec"),
        state_machine_enabled=True,  # F3, 2026-05-21
    ),
    EndpointSpec(
        admin_code="qitech",
        name="market.rentabilidade",
        label="Mercado · Rentabilidade",
        description="Rentabilidade calculada do FIDC.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="09:00",
        canonical_table="wh_rentabilidade_fundo",
        payload_shape_doc_relpath=_shape("market.rentabilidade"),
        state_machine_enabled=True,  # F3, 2026-05-21
    ),
    EndpointSpec(
        admin_code="qitech",
        name="market.rf",
        label="Mercado · Renda fixa",
        description="Posicoes de renda fixa do FIDC — D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:00",
        canonical_table="wh_posicao_renda_fixa",
        payload_shape_doc_relpath=_shape("market.rf"),
        state_machine_enabled=True,  # F3, 2026-05-21
    ),
    EndpointSpec(
        admin_code="qitech",
        name="market.rf_compromissadas",
        label="Mercado · Compromissadas",
        description="Posicoes em operacoes compromissadas — D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:00",
        canonical_table="wh_posicao_compromissada",
        payload_shape_doc_relpath=_shape("market.rf_compromissadas"),
        state_machine_enabled=True,  # F3, 2026-05-21
    ),
    # Estoque do FIDC (carteira de recebiveis cedidos) — fluxo assincrono via
    # job + webhook callback. POST /v2/queue/scheduler/report/fidc-estoque
    # devolve jobId; QiTech processa e chama nosso /webhooks/qitech/job-callback.
    # Ver `report_jobs.py::request_fidc_estoque_report` +
    # `process_fidc_estoque_callback`.
    #
    # Schedule (2026-05-13, info da QiTech): "o fundo processa entre 8h-9h.
    # Automatize a partir das 9h; retry depois das 10h se nao retornar".
    # Daily_at 09:00 cobre a primeira tentativa; o reconciler (Fase 1 do
    # auto-heal) re-tenta se nao chegar dado ate ~09:30/10:00 — sem deduplicar
    # job assincrono ainda em pendente/processing na QiTech (skip guardado em
    # `reconciler.py`). Ver memoria project_qitech_reconciler.md.
    EndpointSpec(
        admin_code="qitech",
        name="market.fidc_estoque",
        label="Mercado · Estoque do FIDC (carteira)",
        description="Posicao consolidada da carteira de recebiveis do FIDC. Disparo assincrono via job + webhook callback.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="09:00",
        canonical_table="wh_estoque_recebivel",
        # Tolerancia mais apertada — fluxo assincrono e mais sensivel a furo
        # (cada disparo pendente segura o reconciler ate timeout do callback).
        default_tolerance_business_days=2,
        default_give_up_business_days=7,
        payload_shape_doc_relpath=_shape("market.fidc_estoque"),
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# Custodia endpoints — familia /v2/fidc-custodia/report/*.
#
# 3 com periodo (data_inicial..data_final), 1 snapshot (sem data). Daily_at
# para cobertura continua — handlers em `adapters/admin/qitech/custodia.py`
# interpretam `since=None` (default do scheduler) como janelas rolantes
# naturalmente curtas: D-7..D-1 pros de periodo (captura correcoes tardias
# da QiTech via upsert idempotente), D-1 pro detalhes, snapshot atual pro
# movimento_aberto. Backfill historico via REST proprio:
# POST /qitech/custodia/{name}/sync com data_inicial/data_final explicitos.
#
# Horarios escalonados (09:30/09:45/10:00) caem 1h depois dos market.* pra
# nao sobrecarregar o pool de conexao em um pico unico.
# ─────────────────────────────────────────────────────────────────────────────

_CUSTODIA_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        admin_code="qitech",
        name="custodia.aquisicao_consolidada",
        label="Custodia · Aquisicoes consolidadas",
        description="Cessoes adquiridas no periodo — granularidade por recebivel. Janela rolante D-7..D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="09:30",
        canonical_table="wh_aquisicao_recebivel",
        payload_shape_doc_relpath=_shape("custodia.aquisicao_consolidada"),
        state_machine_enabled=True,  # F3, 2026-05-21
    ),
    EndpointSpec(
        admin_code="qitech",
        name="custodia.liquidados_baixados",
        label="Custodia · Liquidacoes e baixas",
        description="Liquidacoes e baixas de recebiveis no periodo — granularidade por recebivel. Janela rolante D-7..D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="09:45",
        canonical_table="wh_liquidacao_recebivel",
        payload_shape_doc_relpath=_shape("custodia.liquidados_baixados"),
        state_machine_enabled=True,  # F3, 2026-05-21
    ),
    EndpointSpec(
        admin_code="qitech",
        name="custodia.movimento_aberto",
        label="Custodia · Cessoes em aberto (snapshot)",
        description="Snapshot diario de cessoes pendentes de liquidacao. Sem data no path — cada disparo e foto do estado naquela manha, formando serie temporal.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="10:00",
        canonical_table="wh_movimento_aberto",
        payload_shape_doc_relpath=_shape("custodia.movimento_aberto"),
        state_machine_enabled=True,  # F3, 2026-05-21
    ),
    EndpointSpec(
        admin_code="qitech",
        name="custodia.detalhes_operacoes",
        label="Custodia · Detalhes de operacoes (CNAB)",
        description="Lotes CNAB processados no dia — uma linha por arquivo de remessa. Data alvo D-1.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="10:00",
        canonical_table="wh_operacao_remessa",
        payload_shape_doc_relpath=_shape("custodia.detalhes_operacoes"),
        state_machine_enabled=True,  # F3, 2026-05-21
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Bank-account endpoints (separados do _PIPELINE no etl.py — vivem em
# `bank_account_sync.py`).
# ─────────────────────────────────────────────────────────────────────────────

_BANK_ACCOUNT_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        admin_code="qitech",
        name="bank_account.balance",
        label="Conta-corrente · Saldo",
        description="Saldo de fechamento das contas-corrente Singulare. Disponivel apos ~18h SP.",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="19:00",
        canonical_table="wh_saldo_bancario_diario",
        # End-of-day mesmo dia — D+0 e o esperado, D+1 ja chama atencao.
        default_expected_lag_business_days=0,
        default_tolerance_business_days=1,
        default_give_up_business_days=5,
        payload_shape_doc_relpath=_shape("bank_account.balance"),
    ),
    EndpointSpec(
        admin_code="qitech",
        name="bank_account.statement",
        label="Conta-corrente · Extrato",
        description="Lancamentos da conta-corrente — atualizados ao longo do dia.",
        default_schedule_kind=ScheduleKind.INTERVAL,
        default_schedule_value="60",
        canonical_table="wh_extrato_bancario",
        # Intraday — semanticamente nao tem "data referencia" no mesmo sentido
        # dos market reports. Tolerancia ampla — coverage nao se aplica nesse
        # endpoint hoje (UNSUPPORTED), mas mantemos valores defensivos.
        default_expected_lag_business_days=0,
        default_tolerance_business_days=1,
        default_give_up_business_days=3,
        payload_shape_doc_relpath=_shape("bank_account.statement"),
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Public catalog
# ─────────────────────────────────────────────────────────────────────────────

QITECH_ENDPOINTS: tuple[EndpointSpec, ...] = (
    *_MARKET_ENDPOINTS,
    *_CUSTODIA_ENDPOINTS,
    *_BANK_ACCOUNT_ENDPOINTS,
)


# Index for O(1) lookup by name — used by handlers/dispatch.
QITECH_ENDPOINTS_BY_NAME: dict[str, EndpointSpec] = {
    ep.name: ep for ep in QITECH_ENDPOINTS
}
