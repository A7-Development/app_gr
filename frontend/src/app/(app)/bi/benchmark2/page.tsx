"use client"

// /bi/benchmark2 — Listagem de FIDCs CVM no shell canonico Cota Sub.
//
// Arquitetura (CLAUDE.md sec 11.6 hierarquia 3 niveis):
//   L1 (dropdown): BI
//     L2 (sidebar): Benchmark → /bi/benchmark2
//       L3 (TabNavigation): Fundos (unica aba, espaco reservado pra
//                                    futuras Concentracao | Cotistas).
//
// Shell visual identico ao /controladoria/cota-sub:
//   - h-[calc(100vh-3rem)] flex column
//   - Title row 70px: PageHeader + DashboardHeaderActions (AI/Share/Export)
//   - Toolbar unificada 52px: TabNavigation + FilterChips + SavedViews
//   - Conteudo scrollavel: DataTable de fundos
//   - ProvenanceFooter sticky (status do CVM)
//   - AIPanel drawer in-layout (Cmd/Ctrl+I)
//   - DrillDownSheet (2xl) abre Ficha Lamina ao clicar num fundo
//
// Sub-pagina /bi/benchmark2/[cnpj] foi removida — agora a ficha mora
// dentro do DrillDownSheet desta pagina.

import * as React from "react"
import {
  RiCalendarLine,
  RiCheckLine,
  RiSearchLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"

import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import {
  ProvenanceFooter,
  type ProvenanceSource,
} from "@/design-system/components/ProvenanceFooter"
import {
  FilterChip,
  RemovableChip,
  SavedViewsDropdown,
} from "@/design-system/components/FilterBar"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import {
  AIPanel,
  useAIPanel,
  type AIInsight,
} from "@/design-system/components/AIPanel"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"
import type { Benchmark2FundoRow } from "@/lib/api-client"

import {
  useBenchmark2Fundo,
  useBenchmark2Fundos,
} from "./_components/useBenchmark2"
import { CarteiraLaminaTable } from "./_components/CarteiraLaminaTable"
import { CoberturaSubordinacaoTable } from "./_components/CoberturaSubordinacaoTable"
import { IdentidadeHeader } from "./_components/IdentidadeHeader"

// ───────────────────────────────────────────────────────────────────────────
// Formatters
// ───────────────────────────────────────────────────────────────────────────

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})
const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})
const fmtInt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 })

function fmtCompetencia(yyyymm: string): string {
  if (!yyyymm) return "—"
  const [y, m] = yyyymm.split("-")
  if (!y || !m) return yyyymm
  return new Date(Number(y), Number(m) - 1, 1).toLocaleString("pt-BR", {
    month: "short",
    year: "numeric",
  })
}

function formatCNPJ(v: string): string {
  const s = v.replace(/\D/g, "").padStart(14, "0")
  return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(
    8,
    12,
  )}-${s.slice(12, 14)}`
}

// ───────────────────────────────────────────────────────────────────────────
// Cells custom (badge)
// ───────────────────────────────────────────────────────────────────────────

function CondomBadge({ value }: { value: Benchmark2FundoRow["condom"] }) {
  if (!value) return <span className={tableTokens.cellMuted}>—</span>
  if (value === "aberto") {
    return (
      <span
        className={cx(
          tableTokens.badge,
          "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300",
        )}
      >
        Aberto
      </span>
    )
  }
  return (
    <span
      className={cx(
        tableTokens.badge,
        "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
      )}
    >
      Fechado
    </span>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Mocks (provenance + AI insights)
// ───────────────────────────────────────────────────────────────────────────

const MOCK_PROVENANCE: ProvenanceSource[] = [
  {
    label: "CVM Informe Mensal",
    updated: "atualizacao mensal",
    sla: "30 dias",
    stale: false,
  },
]

const MOCK_INSIGHTS: AIInsight[] = [
  {
    text: "FIDCs com PL > R$ 500mi concentram 62% do mercado total registrado na CVM.",
  },
  {
    text: "Condominio fechado predomina (>80% do PL agregado) — perfil tipico de FIDCs corporativos.",
  },
  {
    text: "Top 10 administradoras respondem por ~70% do volume agregado.",
  },
]

// ───────────────────────────────────────────────────────────────────────────
// Tabs L3 (so 1 por enquanto — Cota Sub style)
// ───────────────────────────────────────────────────────────────────────────

const TABS = [{ key: "fundos", label: "Fundos" }] as const

type TabKey = (typeof TABS)[number]["key"]

const CONDOM_OPTIONS = ["Todos", "Aberto", "Fechado"] as const
type CondomOption = (typeof CONDOM_OPTIONS)[number]

const PAGE_INFO =
  "Mercado FIDC a partir dos Informes Mensais publicados pela CVM. Clique numa linha para abrir a ficha Lamina (Austin Rating style) do fundo. Dado publico, atualizacao mensal."

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<Benchmark2FundoRow>()

export default function Benchmark2Page() {
  const [activeTab, setActiveTab] = React.useState<TabKey>("fundos")
  const [search, setSearch] = React.useState("")
  const [condomFilter, setCondomFilter] =
    React.useState<CondomOption>("Todos")
  const [selectedFundo, setSelectedFundo] =
    React.useState<Benchmark2FundoRow | null>(null)

  const ai = useAIPanel()
  const fundosQuery = useBenchmark2Fundos()
  const data = fundosQuery.data?.fundos ?? []
  const competencia = fundosQuery.data?.competencia ?? ""

  // KPIs agregados do mercado (toda a base CVM, antes dos filtros locais).
  const kpis = React.useMemo(() => {
    const totalFundos = data.length
    const plTotal = data.reduce((s, r) => s + (r.pl_ult_mes ?? 0), 0)
    const cotistasTotal = data.reduce((s, r) => s + (r.cotistas ?? 0), 0)
    const ticketMedio = totalFundos > 0 ? plTotal / totalFundos : 0
    return { totalFundos, plTotal, cotistasTotal, ticketMedio }
  }, [data])

  // Filtros aplicados client-side (a query ja vem sem paginacao).
  const filteredRows = React.useMemo(() => {
    const sNorm = search.toLowerCase().trim()
    const sDigits = search.replace(/\D/g, "")
    return data.filter((r) => {
      if (condomFilter === "Aberto" && r.condom !== "aberto") return false
      if (condomFilter === "Fechado" && r.condom !== "fechado") return false
      if (sNorm) {
        const fundoMatch = r.fundo.toLowerCase().includes(sNorm)
        const cnpjMatch = sDigits
          ? r.cnpj.replace(/\D/g, "").includes(sDigits)
          : false
        if (!fundoMatch && !cnpjMatch) return false
      }
      return true
    })
  }, [data, condomFilter, search])

  // ── Header actions ─────────────────────────────────────────────────────
  const handleShare = React.useCallback(() => {
    void navigator.clipboard?.writeText(window.location.href)
  }, [])

  const handleExport = React.useCallback(() => {
    // Stub — wire to CSV/XLSX endpoint quando necessario.
    // eslint-disable-next-line no-console
    console.log("export benchmark2 listing", {
      competencia,
      condomFilter,
      search,
    })
  }, [competencia, condomFilter, search])

  // ── AI context ─────────────────────────────────────────────────────────
  const aiContext = React.useMemo(
    () => ({
      page: "BI · Benchmark",
      period: competencia ? fmtCompetencia(competencia) : "—",
      filters:
        [
          condomFilter !== "Todos" && `Condominio: ${condomFilter}`,
          search && `Busca: ${search}`,
        ]
          .filter(Boolean)
          .join(", ") || "Nenhum",
    }),
    [competencia, condomFilter, search],
  )

  // ── Saved views ────────────────────────────────────────────────────────
  const currentViewParams = React.useMemo<Record<string, string>>(
    () => ({
      competencia,
      condom: condomFilter,
      search,
    }),
    [competencia, condomFilter, search],
  )

  const handleApplyView = React.useCallback(
    (view: { params: Record<string, string> }) => {
      if (view.params.condom)
        setCondomFilter(view.params.condom as CondomOption)
      if (view.params.search) setSearch(view.params.search)
    },
    [],
  )

  // ── Scroll shadow na toolbar quando o conteudo abaixo scrolla ─────────
  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()

  // ── Columns ────────────────────────────────────────────────────────────
  const columns = React.useMemo<ColumnDef<Benchmark2FundoRow, unknown>[]>(
    () => [
      col.accessor("fundo", {
        header: "Fundo",
        size: 380,
        cell: (info) => (
          <span
            className={cx(tableTokens.cellText, "block max-w-full truncate")}
            title={info.getValue()}
          >
            {info.getValue()}
          </span>
        ),
      }) as ColumnDef<Benchmark2FundoRow, unknown>,

      col.accessor("cnpj", {
        header: "CNPJ",
        size: 160,
        cell: (info) => (
          <span className={tableTokens.cellTextMono}>{info.getValue()}</span>
        ),
      }) as ColumnDef<Benchmark2FundoRow, unknown>,

      col.accessor("condom", {
        header: "Condominio",
        size: 110,
        cell: (info) => <CondomBadge value={info.getValue()} />,
      }) as ColumnDef<Benchmark2FundoRow, unknown>,

      col.accessor("cotistas", {
        header: "Cotistas",
        meta: { align: "right" },
        size: 100,
        cell: (info) => {
          const v = info.getValue()
          if (v == null)
            return <span className={tableTokens.cellMuted}>—</span>
          return (
            <span
              className={cx(tableTokens.cellNumber, "block text-right")}
            >
              {fmtInt.format(v)}
            </span>
          )
        },
      }) as ColumnDef<Benchmark2FundoRow, unknown>,

      col.accessor("pl_medio_3m", {
        header: "PL medio 3M",
        meta: { align: "right" },
        size: 160,
        cell: (info) => {
          const v = info.getValue()
          if (v == null)
            return <span className={tableTokens.cellMuted}>—</span>
          return (
            <span
              className={cx(tableTokens.cellNumber, "block text-right")}
            >
              {fmtBRL.format(v)}
            </span>
          )
        },
      }) as ColumnDef<Benchmark2FundoRow, unknown>,

      col.accessor("pl_ult_mes", {
        header: `PL ${competencia ? fmtCompetencia(competencia) : "ult."}`,
        meta: { align: "right" },
        size: 170,
        cell: (info) => {
          const v = info.getValue()
          if (v == null)
            return <span className={tableTokens.cellMuted}>—</span>
          return (
            <span
              className={cx(
                tableTokens.cellNumber,
                "block text-right font-medium",
              )}
            >
              {fmtBRL.format(v)}
            </span>
          )
        },
      }) as ColumnDef<Benchmark2FundoRow, unknown>,
    ],
    [competencia],
  )

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden">
      {/* Coluna principal */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Title row (70px) */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="Benchmark"
            info={PAGE_INFO}
            subtitle="BI · Mercado FIDC"
            actions={
              <DashboardHeaderActions
                ai={{ open: ai.open, onToggle: ai.toggle }}
                onShare={handleShare}
                onExport={handleExport}
              />
            }
          />
        </div>

        {/* Toolbar unificada (52px) */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex h-[52px] items-center gap-2 px-6">
            <TabNavigation className="border-0">
              {TABS.map((t, i) => (
                <TabNavigationLink
                  key={t.key}
                  href="#"
                  active={activeTab === t.key}
                  onClick={(e) => {
                    e.preventDefault()
                    setActiveTab(t.key)
                  }}
                  title={`Cmd/Ctrl + ${i + 1}`}
                >
                  {t.label}
                </TabNavigationLink>
              ))}
            </TabNavigation>

            <div
              aria-hidden="true"
              className="mx-1 h-5 w-px bg-gray-200 dark:bg-gray-800"
            />

            <FilterChip
              label="Competencia"
              value={competencia ? fmtCompetencia(competencia) : "—"}
              active={false}
              icon={RiCalendarLine}
            >
              <div className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
                Ultima competencia CVM disponivel. Filtro automatico.
              </div>
            </FilterChip>

            <FilterChip
              label="Condominio"
              value={condomFilter}
              active={condomFilter !== "Todos"}
            >
              <div className="py-1">
                {CONDOM_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setCondomFilter(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      condomFilter === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {condomFilter === opt && (
                      <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />
                    )}
                  </button>
                ))}
              </div>
            </FilterChip>

            {search && (
              <RemovableChip
                label="Busca"
                value={search}
                onRemove={() => setSearch("")}
              />
            )}

            <div className="ml-auto flex items-center gap-2">
              <SavedViewsDropdown
                currentParams={currentViewParams}
                onApplyView={handleApplyView}
              />
              <span className="shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
                {fundosQuery.isFetching ? "Atualizando..." : "Atualizado"}
              </span>
            </div>
          </div>
        </div>

        {/* Conteudo scrollavel */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
          {/* MarketStatusHeadline — banda compacta de KPIs do mercado.
              Mesma anatomy do StatusHeadlineCompact da Cota Sub: single line,
              eyebrow 10px uppercase + valor grande, colunas separadas por
              border-l, chip CVM no canto direito. */}
          <MarketStatusHeadline
            competencia={competencia}
            totalFundos={kpis.totalFundos}
            plTotal={kpis.plTotal}
            cotistasTotal={kpis.cotistasTotal}
            ticketMedio={kpis.ticketMedio}
            loading={fundosQuery.isPending}
          />

          <div className="overflow-hidden rounded border border-gray-200 dark:border-gray-800">
            <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 px-4 py-2.5 dark:border-gray-800">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                Fundos CVM
              </h3>
              <span className="rounded-full border border-gray-200 bg-gray-50 px-1.5 text-[11px] text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
                {filteredRows.length}
              </span>

              <div className="ml-2 flex items-center gap-1.5">
                <div className="relative">
                  <RiSearchLine
                    className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-gray-400 dark:text-gray-500"
                    aria-hidden="true"
                  />
                  <input
                    type="search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Buscar por nome ou CNPJ..."
                    className={cx(
                      "h-[26px] w-64 rounded border border-gray-200 bg-white pl-7 pr-2 text-[13px] outline-none transition-colors",
                      "placeholder:text-gray-400 dark:placeholder:text-gray-600",
                      "focus:border-blue-500 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-50",
                    )}
                  />
                </div>
              </div>
            </div>
            <DataTable
              data={filteredRows}
              columns={columns}
              density="compact"
              showColumnManager={false}
              showDensityToggle={false}
              showExport={false}
              virtualize={true}
              onRowClick={setSelectedFundo}
            />
          </div>
        </div>

        <ProvenanceFooter sources={MOCK_PROVENANCE} />
      </div>

      {/* AI Panel — drawer in-layout */}
      <AIPanel
        open={ai.open}
        onClose={() => ai.setOpen(false)}
        context={aiContext}
        insights={MOCK_INSIGHTS}
      />

      {/* Ficha Lamina dentro do DrillDownSheet */}
      <DrillDownSheet
        open={selectedFundo !== null}
        onClose={() => setSelectedFundo(null)}
        size="2xl"
        title={selectedFundo?.fundo}
      >
        {selectedFundo && (
          <FichaContent
            cnpj={selectedFundo.cnpj.replace(/\D/g, "")}
            fallbackName={selectedFundo.fundo}
            fallbackCnpj={selectedFundo.cnpj}
          />
        )}
      </DrillDownSheet>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// MarketStatusHeadline — barra compacta de KPIs do mercado FIDC.
// Espelha a anatomy do <StatusHeadlineCompact> da Cota Sub: single line denso,
// label eyebrow 10px uppercase + valor grande, colunas separadas por border-l,
// chip CVM no canto direito.
// ───────────────────────────────────────────────────────────────────────────

function MarketStatusHeadline({
  competencia,
  totalFundos,
  plTotal,
  cotistasTotal,
  ticketMedio,
  loading = false,
}: {
  competencia: string
  totalFundos: number
  plTotal: number
  cotistasTotal: number
  ticketMedio: number
  loading?: boolean
}) {
  const compLabel = competencia ? fmtCompetencia(competencia) : ""

  return (
    <section
      className={cx(
        "mb-4 flex flex-wrap items-center gap-x-7 gap-y-2 rounded border px-4 py-3",
        "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
      )}
    >
      {/* Coluna 1: PL total — destaque principal (26px) */}
      <div className="flex items-baseline gap-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
            PL total mercado{compLabel ? ` · ${compLabel}` : ""}
          </div>
          {loading ? (
            <div className="mt-1 h-[26px] w-44 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
          ) : (
            <div className="mt-0.5 text-[26px] font-semibold leading-[1.05] tracking-[-0.025em] tabular-nums text-gray-900 dark:text-gray-50">
              {fmtBRLCompact.format(plTotal)}
            </div>
          )}
        </div>

        {/* Coluna 2: Fundos (20px) */}
        <div className="ml-1 border-l border-gray-200 pl-4 dark:border-gray-800">
          <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
            Fundos
          </div>
          {loading ? (
            <div className="mt-1 h-[20px] w-20 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
          ) : (
            <div className="mt-0.5 text-[20px] font-semibold leading-tight tracking-[-0.02em] tabular-nums text-gray-900 dark:text-gray-50">
              {fmtInt.format(totalFundos)}
            </div>
          )}
        </div>

        {/* Coluna 3: Cotistas (20px) */}
        <div className="ml-1 border-l border-gray-200 pl-4 dark:border-gray-800">
          <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
            Cotistas
          </div>
          {loading ? (
            <div className="mt-1 h-[20px] w-24 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
          ) : (
            <div className="mt-0.5 text-[20px] font-semibold leading-tight tracking-[-0.02em] tabular-nums text-gray-900 dark:text-gray-50">
              {fmtInt.format(cotistasTotal)}
            </div>
          )}
        </div>

        {/* Coluna 4: Ticket medio (20px) */}
        <div className="ml-1 border-l border-gray-200 pl-4 dark:border-gray-800">
          <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
            Ticket medio
          </div>
          {loading ? (
            <div className="mt-1 h-[20px] w-24 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
          ) : (
            <div className="mt-0.5 text-[20px] font-semibold leading-tight tracking-[-0.02em] tabular-nums text-gray-900 dark:text-gray-50">
              {fmtBRLCompact.format(ticketMedio)}
            </div>
          )}
        </div>
      </div>

      {/* Chips no canto direito */}
      <div className="ml-auto flex flex-wrap items-center gap-1.5">
        <span
          className={cx(
            "inline-flex items-center gap-1.5 whitespace-nowrap rounded border px-2 py-0.5 text-[11px] font-medium leading-tight",
            "border-emerald-100 bg-emerald-50 text-emerald-700",
            "dark:border-emerald-900/40 dark:bg-emerald-500/10 dark:text-emerald-300",
          )}
        >
          <span
            className="inline-block size-1.5 rounded-full bg-emerald-500"
            aria-hidden="true"
          />
          CVM publico
        </span>
      </div>
    </section>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// FichaContent — conteudo do DrillDownSheet
// Reuso direto dos componentes Lamina (CarteiraLaminaTable, Cobertura, etc).
// ───────────────────────────────────────────────────────────────────────────

function FichaContent({
  cnpj,
  fallbackName,
  fallbackCnpj,
}: {
  cnpj: string
  fallbackName: string
  fallbackCnpj: string
}) {
  const query = useBenchmark2Fundo(cnpj)

  if (query.isPending) {
    return (
      <div className="flex flex-col gap-2 p-6">
        <div className="text-sm font-medium text-gray-900 dark:text-gray-50">
          {fallbackName}
        </div>
        <div className="font-mono text-xs text-gray-500 dark:text-gray-400">
          {formatCNPJ(fallbackCnpj)}
        </div>
        <div className="mt-4 text-sm text-gray-500 dark:text-gray-400">
          Carregando ficha do fundo...
        </div>
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="flex flex-col gap-2 p-6">
        <div className="text-sm font-medium text-gray-900 dark:text-gray-50">
          {fallbackName}
        </div>
        <div className="mt-4 text-sm text-red-600 dark:text-red-400">
          Falha ao carregar ficha:{" "}
          {(query.error as Error)?.message ?? "erro desconhecido"}
        </div>
      </div>
    )
  }

  const ficha = query.data?.data
  if (!ficha) return null

  return (
    <div className="flex flex-col gap-4 overflow-y-auto p-4">
      <IdentidadeHeader ficha={ficha} />
      <CarteiraLaminaTable ficha={ficha} format="brl" />
      <CarteiraLaminaTable ficha={ficha} format="pct" />
      <CoberturaSubordinacaoTable ficha={ficha} />
    </div>
  )
}
