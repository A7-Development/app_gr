// src/design-system/patterns/DashboardBiPadrao.tsx
//
// PATTERN — BI · Pagina padrao (handoff bi-padrao, 2026-04-26).
// Copy, paste, adapt. NAO e black-box: voce vai mexer aqui.
//
// Composicao das 5 zonas canonicas + AI panel violeta in-layout:
//
//   ┌─ Z1 PageHeader (titulo + info + botao IA + acoes) ─────────────────────┐
//   ├─ Z2 TabNavigation L3 (Visao geral · Evolucao · Detalhes) ──────────────┤
//   ├─ Z3 FilterBar sticky (FilterSearch + FilterChip ativos + Mais filtros) ┤
//   ├─ Z4 Conteudo da aba ─────────────────┬─ AI Panel (drawer in-layout) ──┤
//   │   • InsightBar (3 insights violeta) │  • Context chip                 │
//   │   • KpiStrip (5 KPIs c/ sparkline)  │  • Insights expansiveis         │
//   │   • Grid 60/40 (hero + secundario)  │  • Chat com historico           │
//   │   • Grid 3 cols (charts auxiliares) │                                 │
//   │   • DataTable (cessoes + StatusPill)│                                 │
//   ├─ Z5 ProvenanceFooter (mock) ────────┴───────────────────────────────── ┤
//
// HOW TO ADAPT:
//   1. Substitua MOCK_CESSOES por useQuery real (manter shape do row).
//   2. Troque opcoes ECharts (plEvolucaoOption etc) por suas series.
//   3. Atualize TABS para as L3 da pagina.
//   4. Substitua MOCK_INSIGHTS por insights gerados pela sua API.
//   5. Conecte AIPanel.sendMessage no LLM real.
//   6. Remova charts que nao se aplicam — pattern e flexivel.
//
// Cross-filter (CLAUDE.md 14.3): use `useBiFilters()` e os filters
// derivados (`filtersWithFocus*`). Esta versao e standalone para handoff
// (sem dependencia de api-client).
//

"use client"

import * as React from "react"
import {
  RiCalendarLine,
  RiCheckLine,
  RiDownloadLine,
} from "@remixicon/react"
import { toast } from "sonner"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import type { EChartsOption } from "echarts"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"

import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import { ProvenanceFooter, type ProvenanceSource } from "@/design-system/components/ProvenanceFooter"
import { VizParam } from "@/design-system/components/VizParam"
import {
  KpiCard,
  KpiStrip,
  FIDC_KPI_META,
} from "@/design-system/components/KpiStrip"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import {
  FilterBar,
  FilterChip,
  FilterSearch,
  MoreFiltersButton,
  RemovableChip,
} from "@/design-system/components/FilterBar"
import { Insight, InsightBar } from "@/design-system/components/Insight"
import {
  DataTable,
  CurrencyCell,
  DateCell,
  IdCell,
  StatusCell,
} from "@/design-system/components/DataTable"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import {
  AIPanel,
  useAIPanel,
  type AIInsight,
} from "@/design-system/components/AIPanel"
import { tokens, type StatusKey } from "@/design-system/tokens"

// ───────────────────────────────────────────────────────────────────────────
// Mocks — substituir por queries reais
// ───────────────────────────────────────────────────────────────────────────

type CessaoRow = {
  id:         string
  cedente:    string
  sacado:     string
  valor:      number
  vencimento: string | null
  status:     StatusKey
}

const MOCK_CESSOES: CessaoRow[] = [
  { id: "CCB-2024-001234", cedente: "Acme Ltda",     sacado: "Varejo SA",     valor: 45_200,  vencimento: "2026-06-15", status: "em-dia" },
  { id: "CCB-2024-001235", cedente: "BRT Comercio",  sacado: "Tech Corp",     valor: 12_800,  vencimento: "2026-04-30", status: "atrasado-30" },
  { id: "CCB-2024-001236", cedente: "Nexus SA",      sacado: "Foods Ltda",    valor: 78_500,  vencimento: null,         status: "inadimplente" },
  { id: "CCB-2024-001237", cedente: "Delta Ind.",    sacado: "Construcao SA", valor: 33_100,  vencimento: "2026-07-20", status: "em-dia" },
  { id: "CCB-2024-001238", cedente: "Acme Ltda",     sacado: "Retail Plus",   valor: 21_600,  vencimento: "2026-05-10", status: "atrasado-60" },
  { id: "CCB-2024-001239", cedente: "Nexus SA",      sacado: "LogTech",       valor: 55_000,  vencimento: "2026-08-01", status: "liquidado" },
]

const MOCK_INSIGHTS: AIInsight[] = [
  { text: "Inadimplencia de 3,2% (+0,4pp) concentrada em Acme Ltda (31% da carteira) — acima do limite recomendado de 25%." },
  { text: "PDD caiu 5,2% apos recuperacao de R$ 110k no cedente Nexus em mar/26." },
  { text: "Volume de cessoes crescendo pelo 4° mes consecutivo. PL estimado em R$ 130M ate jul/26." },
]

const MOCK_PROVENANCE: ProvenanceSource[] = [
  { label: "Bitfin",   updated: "ha 12 min", sla: "15 min", stale: false },
  { label: "CIP/CERC", updated: "ha 8 min",  sla: "30 min", stale: false },
  { label: "PDD",      updated: "ha 47 min", sla: "30 min", stale: true  },
]

// ───────────────────────────────────────────────────────────────────────────
// L3 Tabs
// ───────────────────────────────────────────────────────────────────────────

const TABS = [
  { key: "visao-geral", label: "Visao geral" },
  { key: "evolucao",    label: "Evolucao" },
  { key: "detalhes",    label: "Detalhes" },
] as const

type TabKey = (typeof TABS)[number]["key"]

// ───────────────────────────────────────────────────────────────────────────
// Filtros (estado simples — a pagina real usa `useBiFilters`)
// ───────────────────────────────────────────────────────────────────────────

const PERIOD_OPTIONS = [
  "Ultimos 30 dias",
  "Ultimos 3 meses",
  "Ultimos 6 meses",
  "Abr 2025 — Abr 2026",
] as const
const FUNDO_OPTIONS  = ["Todos", "FIDC Acme", "FIDC BRT", "FIDC Nexus"] as const
const TIPO_OPTIONS   = ["Multiclasse", "Padronizado", "Nao-padronizado"] as const

type PeriodOption = (typeof PERIOD_OPTIONS)[number]
type FundoOption  = (typeof FUNDO_OPTIONS)[number]
type TipoOption   = (typeof TIPO_OPTIONS)[number]

// ───────────────────────────────────────────────────────────────────────────
// ECharts options (mock — substituir pelos seus)
// ───────────────────────────────────────────────────────────────────────────

const MONTHS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
const CHART_COLORS = tokens.colors.chart

const plEvolucaoOption: EChartsOption = {
  grid: { top: 12, right: 12, bottom: 28, left: 52 },
  xAxis: { type: "category", data: MONTHS, axisTick: { show: false } },
  yAxis: { type: "value", min: 85, axisLabel: { formatter: "{value}M" } },
  series: [
    {
      type: "line", smooth: true, symbol: "none",
      data: [93.1, 96.4, 98.2, 101.5, 105.3, 107.8, 110.2, 114.5, 118.3, 120.1, 122.8, 124.5],
      lineStyle: { color: "#3B82F6", width: 2 },
      areaStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: "rgba(59,130,246,0.20)" },
            { offset: 1, color: "rgba(59,130,246,0)" },
          ],
        },
      },
    },
  ],
  tooltip: { trigger: "axis" },
}

const inadimplenciaAgingOption: EChartsOption = {
  grid: { top: 8, right: 12, bottom: 28, left: 40 },
  xAxis: { type: "category", data: ["1-30d", "31-60d", "61-90d", "91-120d", "120d+"], axisTick: { show: false } },
  yAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
  series: [
    {
      type: "bar", barMaxWidth: 32,
      data: [
        { value: 1.2, itemStyle: { color: "#F59E0B", borderRadius: [3, 3, 0, 0] } },
        { value: 0.8, itemStyle: { color: "#F97316", borderRadius: [3, 3, 0, 0] } },
        { value: 0.4, itemStyle: { color: "#EF4444", borderRadius: [3, 3, 0, 0] } },
        { value: 0.4, itemStyle: { color: "#DC2626", borderRadius: [3, 3, 0, 0] } },
        { value: 0.4, itemStyle: { color: "#B91C1C", borderRadius: [3, 3, 0, 0] } },
      ],
    },
  ],
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
}

const distribCedenteOption: EChartsOption = {
  tooltip: { trigger: "item", formatter: "{b}: {d}%" },
  legend:  { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
  series: [
    {
      type: "pie", radius: ["42%", "70%"], center: ["50%", "44%"],
      label: { show: false },
      data: [
        { name: "Acme Ltda",    value: 31, itemStyle: { color: CHART_COLORS[0] } },
        { name: "BRT Comercio", value: 24, itemStyle: { color: CHART_COLORS[3] } },
        { name: "Nexus SA",     value: 18, itemStyle: { color: CHART_COLORS[2] } },
        { name: "Delta Ind.",   value: 14, itemStyle: { color: CHART_COLORS[5] } },
        { name: "Outros",       value: 13, itemStyle: { color: "#9CA3AF" } },
      ],
    },
  ],
}

const volumeCessoesOption: EChartsOption = {
  grid: { top: 8, right: 12, bottom: 28, left: 40 },
  xAxis: { type: "category", data: MONTHS, axisTick: { show: false } },
  yAxis: { type: "value" },
  series: [
    { name: "Em dia",       type: "bar", stack: "total", data: [420, 432, 401, 454, 490, 530, 510, 540, 580, 610, 650, 720], itemStyle: { color: "#10B981" } },
    { name: "Atrasado",     type: "bar", stack: "total", data: [40, 52, 61, 34, 70, 30, 55, 44, 68, 55, 60, 75],            itemStyle: { color: "#F59E0B" } },
    { name: "Inadimplente", type: "bar", stack: "total", data: [10, 12, 8, 14, 18, 10, 18, 12, 22, 18, 15, 20],             itemStyle: { color: "#EF4444" } },
  ],
  legend:  { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
}

const rentabilidadeOption: EChartsOption = {
  grid: { top: 12, right: 12, bottom: 28, left: 48 },
  xAxis: { type: "category", data: MONTHS, axisTick: { show: false } },
  yAxis: { type: "value", min: 98, axisLabel: { formatter: "{value}%" } },
  series: [
    {
      name: "Fundo", type: "line", smooth: true, symbol: "none",
      data: [101, 103, 105, 104, 107, 109, 108, 111, 112, 113, 112, 114],
      lineStyle: { color: "#3B82F6", width: 2 },
      areaStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: "rgba(59,130,246,0.15)" },
            { offset: 1, color: "rgba(59,130,246,0)" },
          ],
        },
      },
    },
    {
      name: "CDI", type: "line", smooth: true, symbol: "none",
      data: [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111],
      lineStyle: { color: "#9CA3AF", width: 1.5, type: "dashed" },
    },
  ],
  legend:  { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
  tooltip: { trigger: "axis" },
}

// ───────────────────────────────────────────────────────────────────────────
// Tab content components
// ───────────────────────────────────────────────────────────────────────────

const SPARK_PL   = [100, 108, 104, 112, 118, 115, 122, 120, 124, 125, 128, 131]
const SPARK_RENT = [108, 109, 110, 112, 111, 113, 112, 114, 115, 112, 113, 114]
const SPARK_INAD = [2.8, 2.9, 3.0, 2.9, 3.1, 3.0, 3.1, 3.2, 3.1, 3.2, 3.1, 3.2]
const SPARK_PDD  = [2.2, 2.1, 2.0, 2.1, 2.2, 2.1, 2.0, 2.1, 2.1, 2.0, 2.1, 2.1]

function VisaoGeralTab({ onRowClick }: { onRowClick: (row: CessaoRow) => void }) {
  const [plPeriod, setPlPeriod] = React.useState("12M")
  const [volPeriod, setVolPeriod] = React.useState("12M")

  return (
    <div className="flex flex-col gap-3">
      {/* Insight bar */}
      <InsightBar>
        {MOCK_INSIGHTS.map((ins, i) => (
          <Insight key={i} tone="violet" text={ins.text} />
        ))}
      </InsightBar>

      {/* Hero 60/40: PL evolucao + Inadimplencia aging */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <EChartsCard
          title="Evolucao do PL"
          caption="Patrimonio liquido · Bitfin"
          option={plEvolucaoOption}
          height={200}
          className="lg:col-span-2"
          actions={
            <VizParam
              options={["12M", "6M", "3M", "1M"]}
              value={plPeriod}
              onChange={setPlPeriod}
            />
          }
        />
        <EChartsCard
          title="Inadimplencia por aging"
          caption="% sobre carteira total"
          option={inadimplenciaAgingOption}
          height={130}
          footer={
            <div className="flex items-end justify-between pt-2">
              <div>
                <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  Inadimp. total
                </div>
                <div className="text-lg font-semibold tabular-nums text-red-600 dark:text-red-400">
                  3,2%
                </div>
              </div>
              <div>
                <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  Aging 120d+
                </div>
                <div className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                  1,8%
                </div>
              </div>
            </div>
          }
        />
      </div>

      {/* Secondary row — 3 charts */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <EChartsCard
          title="Distribuicao por cedente"
          caption="Top 5 cedentes · participacao %"
          option={distribCedenteOption}
          height={200}
        />
        <EChartsCard
          title="Volume de cessoes"
          caption="Em dia · Atrasado · Inadimplente"
          option={volumeCessoesOption}
          height={200}
          actions={
            <VizParam
              options={["12M", "6M", "3M"]}
              value={volPeriod}
              onChange={setVolPeriod}
            />
          }
        />
        <EChartsCard
          title="Rentabilidade acum. vs CDI"
          caption="Base 100 · jan/26"
          option={rentabilidadeOption}
          height={200}
        />
      </div>

      {/* Tabela */}
      <div className="rounded border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-2.5 dark:border-gray-800">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">Cessoes</h3>
          <span className="rounded-full border border-gray-200 bg-gray-50 px-1.5 text-[11px] text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
            {MOCK_CESSOES.length}
          </span>
          <Button variant="ghost" className="ml-auto">
            <RiDownloadLine className="size-3.5" aria-hidden="true" />
            Exportar
          </Button>
        </div>
        <DataTable
          data={MOCK_CESSOES}
          columns={CESSOES_COLUMNS}
          density="compact"
          showColumnManager={false}
          showDensityToggle={false}
          showExport={false}
          virtualize={false}
          onRowClick={onRowClick}
        />
      </div>
    </div>
  )
}

function PlaceholderTab({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <div className="size-10 rounded-full bg-gray-100 dark:bg-gray-800" aria-hidden="true" />
      <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
        Visao &quot;{label}&quot;
      </p>
      <p className="text-xs text-gray-400 dark:text-gray-600">
        Adapte esta aba para o contexto analitico correspondente.
      </p>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// DataTable columns
// ───────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<CessaoRow>()

const CESSOES_COLUMNS: ColumnDef<CessaoRow, unknown>[] = [
  col.accessor("id", {
    header: "ID",
    size:   150,
    cell:   (info) => <IdCell value={info.getValue<string>()} />,
  }) as ColumnDef<CessaoRow, unknown>,
  col.accessor("cedente", {
    header: "Cedente",
    size:   160,
  }) as ColumnDef<CessaoRow, unknown>,
  col.accessor("sacado", {
    header: "Sacado",
    size:   140,
    cell:   (info) => (
      <span className="text-sm text-gray-500 dark:text-gray-400">
        {info.getValue<string>()}
      </span>
    ),
  }) as ColumnDef<CessaoRow, unknown>,
  col.accessor("valor", {
    header: "Valor",
    size:   120,
    cell:   (info) => <CurrencyCell value={info.getValue<number>()} />,
  }) as ColumnDef<CessaoRow, unknown>,
  col.accessor("vencimento", {
    header: "Vencimento",
    size:   110,
    cell:   (info) => <DateCell value={info.getValue<string | null>()} />,
  }) as ColumnDef<CessaoRow, unknown>,
  col.accessor("status", {
    header: "Status",
    size:   140,
    cell:   (info) => <StatusCell value={info.getValue<StatusKey>()} />,
  }) as ColumnDef<CessaoRow, unknown>,
]

// ───────────────────────────────────────────────────────────────────────────
// Provenance footer (mock — pagina real usa <ProvenanceFooter /> do bi/)
// ───────────────────────────────────────────────────────────────────────────

// ───────────────────────────────────────────────────────────────────────────
// DashboardBiPadrao — page-level pattern
// ───────────────────────────────────────────────────────────────────────────

export function DashboardBiPadrao() {
  // Filtros (estado local — pagina real usa `useBiFilters`).
  const [search, setSearch] = React.useState("")
  const [period, setPeriod] = React.useState<PeriodOption>("Ultimos 30 dias")
  const [fundo,  setFundo]  = React.useState<FundoOption>("Todos")
  const [tipo,   setTipo]   = React.useState<TipoOption>("Multiclasse")

  // Tab L3 ativa.
  const [activeTab, setActiveTab] = React.useState<TabKey>("visao-geral")

  // Atalhos Cmd/Ctrl + 1..3 para tabs (alinhado com regra L3 do CLAUDE.md).
  React.useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && ["1", "2", "3"].includes(e.key)) {
        const idx = Number(e.key) - 1
        if (TABS[idx]) {
          e.preventDefault()
          setActiveTab(TABS[idx].key)
        }
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [])

  // AI panel (open + ⌘I + localStorage).
  const ai = useAIPanel()

  // Drill-down sheet.
  const [selected, setSelected] = React.useState<CessaoRow | null>(null)

  const aiContext = React.useMemo(
    () => ({
      page: "BI · Pagina padrao",
      period,
      filters: [
        fundo !== "Todos" && `Fundo: ${fundo}`,
        tipo !== "Multiclasse" && `Tipo: ${tipo}`,
        search && `Busca: ${search}`,
      ].filter(Boolean).join(", ") || "Nenhum",
    }),
    [period, fundo, tipo, search],
  )

  const handleShare = React.useCallback(() => {
    // Stub: substituir por dialog de compartilhamento real (Slack, email, etc).
    toast.info("Compartilhar — em breve")
  }, [])

  const handleExport = React.useCallback(() => {
    // Stub: substituir por menu de export (CSV, PDF, PNG do dashboard).
    toast.info("Exportar — em breve")
  }, [])

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Coluna principal */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">

        {/* Z1 — PageHeader */}
        <div className="shrink-0 px-6 pt-5 pb-3">
          <PageHeader
            title="BI · Pagina padrao"
            info="Template canonico de dashboard BI: KPIs + insights IA + grid 60/40 + tabela + drill-down."
            actions={
              <DashboardHeaderActions
                ai={{ open: ai.open, onToggle: ai.toggle }}
                onShare={handleShare}
                onExport={handleExport}
              />
            }
          />
        </div>

        {/* Z2 — TabNavigation L3 */}
        <div className="shrink-0 px-6">
          <TabNavigation>
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
        </div>

        {/* Z3 — FilterBar sticky */}
        <div className="shrink-0 px-6">
          <FilterBar>
            <FilterSearch
              placeholder="Buscar cessoes..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onClear={() => setSearch("")}
            />

            <FilterChip
              label="Periodo"
              value={period}
              active={period !== "Ultimos 30 dias"}
              icon={RiCalendarLine}
            >
              <div className="py-1">
                {PERIOD_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setPeriod(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      period === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {period === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            <FilterChip
              label="Fundo"
              value={fundo}
              active={fundo !== "Todos"}
            >
              <div className="py-1">
                {FUNDO_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setFundo(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      fundo === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {fundo === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            <FilterChip
              label="Tipo"
              value={tipo}
              active={tipo !== "Multiclasse"}
            >
              <div className="py-1">
                {TIPO_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setTipo(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      tipo === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {tipo === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
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

            <MoreFiltersButton />
          </FilterBar>
        </div>

        {/* Z4 — Conteudo da aba */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div className="flex flex-col gap-4">
            {/* KpiStrip — 5 KPIs (override grid) */}
            <KpiStrip className="grid-cols-2 min-[720px]:grid-cols-3 lg:grid-cols-5 xl:grid-cols-5">
              <KpiCard
{...FIDC_KPI_META.pl}
                value="R$ 124,5M"
                delta={{ value: 2.34, suffix: "%" }}
                sparkData={SPARK_PL}
                sparkColor="#059669"
                source="Bitfin"
              />
              <KpiCard
{...FIDC_KPI_META.rentabilidade}
                value="112,4%"
                delta={{ value: 3.1, suffix: "pp" }}
                sparkData={SPARK_RENT}
                sparkColor="#3B82F6"
              />
              <KpiCard
{...FIDC_KPI_META.inadimplencia}
                value="3,2%"
                currentValue={3.2}
                delta={{ value: 0.4, suffix: "pp", direction: "up", good: false }}
                sparkData={SPARK_INAD}
                sparkColor="#DC2626"
              />
              <KpiCard
label="PDD"
                deltaSub="vs mes anterior"
                value="R$ 2,1M"
                delta={{ value: 5.2, suffix: "%", direction: "down", good: true }}
                sparkData={SPARK_PDD}
                sparkColor="#F59E0B"
                intensity={{ tone: "neg", level: "low" }}
              />
              <KpiCard
label="Cessoes Pendentes"
                deltaSub="vs semana anterior"
                value="42"
                currentValue={42}
                delta={{ value: 12, suffix: "", direction: "up", good: false }}
                alertThreshold={{ value: 30, severity: "warn" }}
                intensity={{ tone: "neg", level: "mid" }}
              />
            </KpiStrip>

            {/* Tab content */}
            {activeTab === "visao-geral" && <VisaoGeralTab onRowClick={setSelected} />}
            {activeTab === "evolucao"    && <PlaceholderTab label="Evolucao" />}
            {activeTab === "detalhes"    && <PlaceholderTab label="Detalhes" />}
          </div>
        </div>

        {/* Z5 — ProvenanceFooter (mock para handoff) */}
        <ProvenanceFooter sources={MOCK_PROVENANCE} />
      </div>

      {/* AI Panel — drawer in-layout */}
      <AIPanel
        open={ai.open}
        onClose={() => ai.setOpen(false)}
        context={aiContext}
        insights={MOCK_INSIGHTS}
      />

      {/* Drill-down sheet */}
      <DrillDownSheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.id ?? "Cessao"}
      >
        {selected && (
          <div className="flex flex-col gap-4 p-6">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
                {selected.id}
              </p>
              <p className="mt-1 text-base font-semibold text-gray-900 dark:text-gray-50">
                {selected.cedente}
              </p>
              <p className="mt-2 text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                {selected.valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}
              </p>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Vencimento: {selected.vencimento ?? "—"}
              </p>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Stub do drill-down. Em produção, compor com{" "}
              <code className="font-mono">DrillDownHeader</code>,{" "}
              <code className="font-mono">DrillDownHero</code>,{" "}
              <code className="font-mono">DrillDownTabs</code>,{" "}
              <code className="font-mono">DrillDownBody</code>.
            </p>
          </div>
        )}
      </DrillDownSheet>
    </div>
  )
}
