"""Report catalog — declarative catalog of analytical reports surfaced in `/controladoria/relatorios`.

Each `ReportSpec` is one row in the user-facing catalog (`<RelatorioCard>` in
the frontend). Specs are **frozen** and declared at module load time, mirroring
the design of `app/shared/endpoint_catalog.py` (CLAUDE.md §13).

Why code-defined and not a DB table:
    - Catalog is small (~17 rows today, all driven by adapters) and changes
      only when an adapter changes — i.e., on deploy.
    - No per-tenant variation of the catalog itself (visibility filtering is
      runtime, via `is_source_enabled` + `user_module_permission`).
    - Avoids the migration + seed dance for every new report.

A spec maps a user-facing report to:
    - The administradora it comes from (`administradora`)
    - The adapter endpoint that ingested it (`endpoint_name` — matches
      `endpoint_catalog.py::EndpointSpec.name` for sync endpoints)
    - The silver canonical table it reads from (`canonical_table`)
    - Optional date column for `?periodo_inicio/&periodo_fim` filtering
    - Optional fund column for `?fundo_id` filtering

The frontend defines column TS-types per slug in
`frontend/src/lib/reports/<slug>.ts` (decisao 2026-05-09).

Both tabs of `/controladoria/relatorios` (Padronizados / Espelho da
Administradora) read the SAME catalog — the difference is rendering only
(Opcao A — lente operacional).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.enums import Permission, SourceType


class ReportCategory(StrEnum):
    """Semantic category of a report — drives the SegmentSwitch in the catalog page.

    Adding a category here requires adding the corresponding token in
    `frontend/src/design-system/tokens/reportCategoryTokens.ts`.
    """

    COTA = "cota"
    POSICAO = "posicao"
    ESTOQUE = "estoque"
    EVENTOS = "eventos"          # placeholder — no QiTech report alocated yet
    RECEBIMENTOS = "recebimentos"
    CUSTODIA = "custodia"
    MOVIMENTACOES = "movimentacoes"
    OUTROS = "outros"


class ReportRefreshKind(StrEnum):
    """How fresh data arrives for this report.

    DAILY / INTERVAL  — pulled by `sync_dispatcher` from `endpoint_catalog`.
    ON_DEMAND_ASYNC   — triggered manually via REST + processed via callback
                        (`qitech_report_job` model + `routers/webhooks.py`).
    """

    DAILY = "daily"
    INTERVAL = "interval"
    ON_DEMAND_ASYNC = "on_demand_async"


@dataclass(frozen=True)
class ReportSpec:
    """One report exposed in the `/controladoria/relatorios` catalog.

    Attributes:
        slug: URL-safe stable id. Convention `<admin>-<categoria>-<entidade>`.
            Persisted in URLs — never rename without redirect.
        name: pt-BR display name shown in the card and page header.
        description: 1-2 sentence pt-BR description.
        category: Semantic group for the SegmentSwitch.
        administradora: SourceType this report comes from. Used to filter by
            tenant subscription (`is_source_enabled`).
        endpoint_name: Identifier of the underlying adapter endpoint. For
            QiTech sync endpoints, matches `EndpointSpec.name`. For async
            (callback) reports like `fidc_estoque`, matches the QiTech
            `eventType` (camelCase elsewhere; we use snake_case here for
            consistency with our catalog naming).
        canonical_table: Silver table populated by the mapper. Service layer
            queries this table directly (silver-only — §13.2.1).
        refresh_kind: How fresh data arrives.
        date_column: Optional column on `canonical_table` used for date-range
            filtering (`?periodo_inicio/&periodo_fim`). None means the report
            does not support date filters.
        fund_column: Optional column on `canonical_table` used for filtering
            by a specific fund. Two flavors:
              * `"fundo_doc"` — CNPJ digits-only string (most async reports)
              * `"unidade_administrativa_id"` — internal UUID (cota-sub
                 family; not currently used by QiTech)
            None means the report is not fund-scoped.
        default_permission: Minimum permission to read the report.
    """

    slug: str
    name: str
    description: str
    category: ReportCategory
    administradora: SourceType
    endpoint_name: str
    canonical_table: str
    refresh_kind: ReportRefreshKind
    date_column: str | None
    fund_column: str | None
    default_permission: Permission = Permission.READ


# ─────────────────────────────────────────────────────────────────────────────
# QiTech reports
# ─────────────────────────────────────────────────────────────────────────────
# 12 sync endpoints (10 market + 2 bank_account) + 5 async (callback) reports.
# Mapping confirmed in `backend/docs/relatorios-controladoria-catalog.md` and
# verified against `adapters/admin/qitech/endpoint_catalog.py` + each mapper
# (2026-05-09).

_QITECH_SYNC_REPORTS: tuple[ReportSpec, ...] = (
    ReportSpec(
        slug="qitech-cota-outros-fundos",
        name="Posicao em outros fundos",
        description="Posicao do FIDC em cotas de outros fundos investidos — relatorio D-1.",
        category=ReportCategory.COTA,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="market.outros_fundos",
        canonical_table="wh_posicao_cota_fundo",
        refresh_kind=ReportRefreshKind.DAILY,
        date_column="data_referencia",
        fund_column="unidade_administrativa_id",
    ),
    ReportSpec(
        slug="qitech-posicao-conta-corrente",
        name="Saldo em conta-corrente",
        description="Saldo de conta-corrente do FIDC — relatorio D-1.",
        category=ReportCategory.POSICAO,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="market.conta_corrente",
        canonical_table="wh_saldo_conta_corrente",
        refresh_kind=ReportRefreshKind.DAILY,
        date_column="data_referencia",
        fund_column="unidade_administrativa_id",
    ),
    ReportSpec(
        slug="qitech-posicao-tesouraria",
        name="Posicao de tesouraria",
        description="Posicao de tesouraria do FIDC — relatorio D-1.",
        category=ReportCategory.POSICAO,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="market.tesouraria",
        canonical_table="wh_saldo_tesouraria",
        refresh_kind=ReportRefreshKind.DAILY,
        date_column="data_referencia",
        fund_column="unidade_administrativa_id",
    ),
    ReportSpec(
        slug="qitech-posicao-outros-ativos",
        name="Outros ativos em carteira",
        description="Posicoes diversas nao classificadas em renda fixa/variavel.",
        category=ReportCategory.POSICAO,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="market.outros_ativos",
        canonical_table="wh_posicao_outros_ativos",
        refresh_kind=ReportRefreshKind.DAILY,
        date_column="data_referencia",
        fund_column="unidade_administrativa_id",
    ),
    ReportSpec(
        slug="qitech-mov-demonstrativo-caixa",
        name="Demonstrativo de caixa",
        description="Movimentacao de caixa do FIDC — entradas/saidas D-1.",
        category=ReportCategory.MOVIMENTACOES,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="market.demonstrativo_caixa",
        canonical_table="wh_movimento_caixa",
        refresh_kind=ReportRefreshKind.DAILY,
        date_column="data_movimento",
        fund_column="unidade_administrativa_id",
    ),
    ReportSpec(
        slug="qitech-custodia-cpr",
        name="CPR — Contas a pagar e receber",
        description="Contas a pagar e receber — movimento D-1.",
        category=ReportCategory.CUSTODIA,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="market.cpr",
        canonical_table="wh_cpr_movimento",
        refresh_kind=ReportRefreshKind.DAILY,
        date_column="data_referencia",
        fund_column="unidade_administrativa_id",
    ),
    ReportSpec(
        slug="qitech-cota-evolucao",
        name="MEC — Evolucao de cotas",
        description="Mapa evolutivo de cotas do FIDC — relatorio D-1.",
        category=ReportCategory.COTA,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="market.mec",
        canonical_table="wh_mec_evolucao_cotas",
        refresh_kind=ReportRefreshKind.DAILY,
        date_column="data_referencia",
        fund_column="unidade_administrativa_id",
    ),
    ReportSpec(
        slug="qitech-outros-rentabilidade",
        name="Rentabilidade do fundo",
        description="Rentabilidade calculada do FIDC.",
        category=ReportCategory.OUTROS,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="market.rentabilidade",
        canonical_table="wh_rentabilidade_fundo",
        refresh_kind=ReportRefreshKind.DAILY,
        date_column="data_referencia",
        fund_column="unidade_administrativa_id",
    ),
    ReportSpec(
        slug="qitech-posicao-renda-fixa",
        name="Posicao em renda fixa",
        description="Posicoes de renda fixa do FIDC — D-1.",
        category=ReportCategory.POSICAO,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="market.rf",
        canonical_table="wh_posicao_renda_fixa",
        refresh_kind=ReportRefreshKind.DAILY,
        date_column="data_referencia",
        fund_column="unidade_administrativa_id",
    ),
    ReportSpec(
        slug="qitech-posicao-compromissadas",
        name="Posicao em compromissadas",
        description="Operacoes compromissadas em carteira — D-1.",
        category=ReportCategory.POSICAO,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="market.rf_compromissadas",
        canonical_table="wh_posicao_compromissada",
        refresh_kind=ReportRefreshKind.DAILY,
        date_column="data_referencia",
        fund_column="unidade_administrativa_id",
    ),
    ReportSpec(
        slug="qitech-recebimentos-saldo-banco",
        name="Saldo bancario (D-1)",
        description="Saldo de fechamento das contas-corrente Singulare.",
        category=ReportCategory.RECEBIMENTOS,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="bank_account.balance",
        canonical_table="wh_bank_account_balance",
        refresh_kind=ReportRefreshKind.DAILY,
        date_column="data_referencia",
        fund_column=None,  # bank_account.balance is account-scoped, not fund-scoped
    ),
    ReportSpec(
        slug="qitech-mov-extrato-banco",
        name="Extrato bancario",
        description="Lancamentos das contas-corrente Singulare — atualizados ao longo do dia.",
        category=ReportCategory.MOVIMENTACOES,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="bank_account.statement",
        canonical_table="wh_bank_account_statement",
        refresh_kind=ReportRefreshKind.INTERVAL,
        date_column="data_lancamento",
        fund_column=None,  # bank_account.statement is account-scoped
    ),
)


_QITECH_ASYNC_REPORTS: tuple[ReportSpec, ...] = (
    ReportSpec(
        slug="qitech-estoque-carteira",
        name="Carteira de recebiveis",
        description="Snapshot diario dos recebiveis em carteira do FIDC. Disparado via callback (eventType=fidcEstoque).",
        category=ReportCategory.ESTOQUE,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="fidc_estoque",
        canonical_table="wh_estoque_recebivel",
        refresh_kind=ReportRefreshKind.ON_DEMAND_ASYNC,
        date_column="data_referencia",
        fund_column="fundo_doc",
    ),
    ReportSpec(
        slug="qitech-mov-liquidados",
        name="Recebiveis liquidados e baixados",
        description="Liquidacoes e baixas de recebiveis no periodo — granularidade por recebivel.",
        category=ReportCategory.MOVIMENTACOES,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="liquidados_baixados",
        canonical_table="wh_liquidacao_recebivel",
        refresh_kind=ReportRefreshKind.ON_DEMAND_ASYNC,
        date_column="data_posicao",
        fund_column="fundo_doc",
    ),
    ReportSpec(
        slug="qitech-mov-remessas",
        name="Operacoes de remessa (CNAB)",
        description="Lotes CNAB processados no dia — uma linha por arquivo de remessa.",
        category=ReportCategory.MOVIMENTACOES,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="detalhes_operacoes",
        canonical_table="wh_operacao_remessa",
        refresh_kind=ReportRefreshKind.ON_DEMAND_ASYNC,
        date_column="data_importacao",
        fund_column="fundo_doc",
    ),
    ReportSpec(
        slug="qitech-mov-aquisicoes",
        name="Aquisicoes consolidadas",
        description="Cessoes adquiridas no periodo — granularidade por recebivel.",
        category=ReportCategory.MOVIMENTACOES,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="aquisicao_consolidada",
        canonical_table="wh_aquisicao_recebivel",
        refresh_kind=ReportRefreshKind.ON_DEMAND_ASYNC,
        date_column="data_aquisicao",
        fund_column="fundo_doc",
    ),
    ReportSpec(
        slug="qitech-mov-pendentes",
        name="Cessoes pendentes (em aberto)",
        description="Snapshot diario de cessoes pendentes de liquidacao do FIDC.",
        category=ReportCategory.MOVIMENTACOES,
        administradora=SourceType.ADMIN_QITECH,
        endpoint_name="movimento_aberto",
        canonical_table="wh_movimento_aberto",
        refresh_kind=ReportRefreshKind.ON_DEMAND_ASYNC,
        date_column="data_referencia",
        fund_column="fundo_doc",
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Public catalog
# ─────────────────────────────────────────────────────────────────────────────

REPORTS: tuple[ReportSpec, ...] = (
    *_QITECH_SYNC_REPORTS,
    *_QITECH_ASYNC_REPORTS,
)


# Index for O(1) slug -> spec lookup. Used by the controladoria service when
# resolving `/relatorios/<slug>` requests.
REPORTS_BY_SLUG: dict[str, ReportSpec] = {r.slug: r for r in REPORTS}


def reports_for_source(source: SourceType) -> list[ReportSpec]:
    """Return all reports tied to a given administradora.

    Used by `list_reports` in `integracoes/public.py` to filter by tenant
    subscription.
    """
    return [r for r in REPORTS if r.administradora == source]
