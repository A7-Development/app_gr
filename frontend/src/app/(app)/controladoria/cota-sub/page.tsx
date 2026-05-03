// src/app/(app)/controladoria/cota-sub/page.tsx
//
// Controladoria · Cota Sub — analise da cota subordinada do FIDC.
// Pagina derivada do pattern `DashboardBiPadrao` (handoff bi-padrao 2026-04-26).
//
// HOW TO ADAPT (mocks → queries reais):
//   1. Substituir MOCK_MOVIMENTACOES por useQuery contra endpoint
//      /controladoria/cota-sub/movimentacoes (futuro).
//   2. Substituir MOCK_INSIGHTS por insights gerados pela IA (server-side LLM).
//   3. Substituir MOCK_PROVENANCE por status real dos adapters
//      (Bitfin, QiTech, PDD).
//   4. Substituir series ECharts por dados de wh_posicao_cota_fundo +
//      wh_movimentacao_cotista (warehouse silver).
//   5. Conectar AIPanel.sendMessage no LLM real (api.aiChat).
//
// L3 tabs por agora: Diario · Evolucao · Cotistas. Quando outras
// dimensoes (por classe, por sacado da operacao, por safra) entrarem,
// basta adicionar entradas em TABS — pagina nao precisa de refactor.

"use client"

import * as React from "react"
import {
  RiCalendarLine,
  RiCheckLine,
  RiDownloadLine,
  RiEqualizerLine,
  RiFundsLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import type { EChartsOption } from "echarts"

import { format, isSameDay } from "date-fns"
import { ptBR } from "date-fns/locale"

import { cx, focusRing } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import { Calendar } from "@/components/tremor/Calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
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
} from "@/design-system/components/KpiStrip"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import {
  FilterBar,
  FilterChip,
  FilterSearch,
  RemovableChip,
  SavedViewsDropdown,
} from "@/design-system/components/FilterBar"
import { EmptyState } from "@/design-system/components/EmptyState"
import { Insight, InsightBar } from "@/design-system/components/Insight"
import { useUAs } from "@/lib/hooks/cadastros"
import { useBalanco, useVariacoesDia } from "@/lib/hooks/controladoria"
import type { VariacoesDiaResponse } from "@/lib/api-client"
import {
  CurrencyCell,
  DataTable,
  DateCell,
  IdCell,
  StatusCell,
} from "@/design-system/components/DataTable"
import {
  DrillDownSheet,
  type TimelineEventDef,
} from "@/design-system/components/DrillDownSheet"
import {
  AIPanel,
  useAIPanel,
  type AIInsight,
} from "@/design-system/components/AIPanel"
import { tokens, type StatusKey } from "@/design-system/tokens"
import { BalanceTable, type BalanceRow } from "./_components/BalanceTable"
import { PagamentosDiaPanel } from "@/components/controladoria/PagamentosDiaPanel"

// ───────────────────────────────────────────────────────────────────────────
// Tipos + Mocks
// ───────────────────────────────────────────────────────────────────────────

type MovimentacaoTipo = "subscricao" | "resgate"

type MovimentacaoRow = {
  id:      string
  cotista: string
  classe:  "Mezanino" | "Junior"
  tipo:    MovimentacaoTipo
  valor:   number
  data:    string
  status:  StatusKey
}

const MOCK_MOVIMENTACOES: MovimentacaoRow[] = [
  { id: "MOV-2026-000821", cotista: "Aurora Capital",        classe: "Mezanino", tipo: "subscricao", valor:   850_000, data: "2026-04-22", status: "liquidado" },
  { id: "MOV-2026-000822", cotista: "Vanguard FII",          classe: "Junior",   tipo: "subscricao", valor:   320_000, data: "2026-04-20", status: "em-dia" },
  { id: "MOV-2026-000823", cotista: "Helios Asset",          classe: "Mezanino", tipo: "resgate",    valor:   180_000, data: "2026-04-18", status: "em-dia" },
  { id: "MOV-2026-000824", cotista: "Atlas Investimentos",   classe: "Junior",   tipo: "resgate",    valor:    95_000, data: "2026-04-15", status: "liquidado" },
  { id: "MOV-2026-000825", cotista: "Aurora Capital",        classe: "Mezanino", tipo: "subscricao", valor: 1_200_000, data: "2026-04-10", status: "liquidado" },
  { id: "MOV-2026-000826", cotista: "Polaris Family Office", classe: "Junior",   tipo: "subscricao", valor:   540_000, data: "2026-04-08", status: "liquidado" },
]

const MOCK_INSIGHTS: AIInsight[] = [
  { text: "Subordinacao efetiva em 15,0% (+0,3pp), acima do minimo regulamentar de 10%. Margem confortavel para absorver perdas." },
  { text: "Rentabilidade da Cota Sub em 118,2% do CDI — 3 meses consecutivos batendo o benchmark." },
  { text: "Top 3 cotistas concentram 62% do PL subordinado — acima do alerta interno de 50%. Considerar diversificacao." },
]

const MOCK_PROVENANCE: ProvenanceSource[] = [
  { label: "Bitfin", updated: "ha 12 min", sla: "15 min", stale: false },
  { label: "QiTech", updated: "ha 8 min",  sla: "30 min", stale: false },
  { label: "PDD",    updated: "ha 47 min", sla: "30 min", stale: true  },
]

// ───────────────────────────────────────────────────────────────────────────
// L3 Tabs
// ───────────────────────────────────────────────────────────────────────────

const TABS = [
  { key: "diario",   label: "Diario" },
  { key: "evolucao", label: "Evolucao" },
  { key: "cotistas", label: "Cotistas" },
] as const

type TabKey = (typeof TABS)[number]["key"]

// ───────────────────────────────────────────────────────────────────────────
// Filtros
// ───────────────────────────────────────────────────────────────────────────

const CLASSE_OPTIONS = ["Todas", "Subordinada Mezanino", "Subordinada Junior"] as const

type ClasseOption = (typeof CLASSE_OPTIONS)[number]

// Filtros dinamicos (adicionados via "Mais filtros"). Default values
// definem o "Todos/Nenhum" do filtro — quando o user troca, o chip vira
// active e ganha botao de remover.
type DynamicFilterKey = "Cotista" | "Status" | "Classe op." | "Origem"

const DYNAMIC_FILTER_OPTIONS: Record<DynamicFilterKey, readonly string[]> = {
  Cotista:     ["Todos", "Aurora Capital", "Vanguard FII", "Helios Asset", "Atlas Investimentos", "Polaris Family Office"],
  Status:      ["Todos", "Em dia", "Liquidado", "Atrasado", "Inadimplente"],
  "Classe op.": ["Todas", "Multiclasse", "Padronizado", "Nao-padronizado"],
  Origem:      ["Todas", "QiTech", "Bitfin", "Manual"],
}

type DynamicFilter = { key: DynamicFilterKey; value: string }

// Filtros inline na DataTable (Status / Cotista) — mesmas opcoes que
// os dinamicos, mas com escopo limitado a tabela (nao reaplicam a charts).
const TABLE_STATUS_OPTIONS  = DYNAMIC_FILTER_OPTIONS.Status
const TABLE_COTISTA_OPTIONS = DYNAMIC_FILTER_OPTIONS.Cotista

// ───────────────────────────────────────────────────────────────────────────
// ECharts options (mock — substituir pelas series reais)
// ───────────────────────────────────────────────────────────────────────────

const MONTHS = ["Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez", "Jan", "Fev", "Mar", "Abr"]
const CHART_COLORS = tokens.colors.chart

const plCotaSubOption: EChartsOption = {
  grid: { top: 12, right: 12, bottom: 28, left: 52 },
  xAxis: { type: "category", data: MONTHS, axisTick: { show: false } },
  yAxis: { type: "value", min: 14, axisLabel: { formatter: "R$ {value}M" } },
  series: [
    {
      type: "line", smooth: true, symbol: "none",
      data: [14.8, 15.2, 15.6, 15.9, 16.2, 16.5, 16.8, 17.1, 17.4, 17.9, 18.3, 18.7],
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

const distribClasseOption: EChartsOption = {
  tooltip: { trigger: "item", formatter: "{b}: {d}%" },
  legend:  { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
  series: [
    {
      type: "pie", radius: ["42%", "70%"], center: ["50%", "44%"],
      label: { show: false },
      data: [
        { name: "Mezanino", value: 68, itemStyle: { color: CHART_COLORS[0] } },
        { name: "Junior",   value: 32, itemStyle: { color: CHART_COLORS[3] } },
      ],
    },
  ],
}

const subscRescOption: EChartsOption = {
  grid: { top: 8, right: 12, bottom: 28, left: 48 },
  xAxis: { type: "category", data: MONTHS, axisTick: { show: false } },
  yAxis: { type: "value", axisLabel: { formatter: "R$ {value}M" } },
  series: [
    { name: "Subscricao", type: "bar", data: [1.2, 0.8, 1.4, 1.0, 1.6, 1.3, 1.5, 1.1, 1.8, 1.4, 2.1, 2.4], itemStyle: { color: "#10B981" } },
    { name: "Resgate",    type: "bar", data: [0.3, 0.5, 0.4, 0.6, 0.4, 0.5, 0.7, 0.6, 0.5, 0.8, 0.6, 0.7], itemStyle: { color: "#EF4444" } },
  ],
  legend:  { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
}

const rentabSubOption: EChartsOption = {
  grid: { top: 12, right: 12, bottom: 28, left: 48 },
  xAxis: { type: "category", data: MONTHS, axisTick: { show: false } },
  yAxis: { type: "value", min: 100, axisLabel: { formatter: "{value}%" } },
  series: [
    {
      name: "Cota Sub", type: "line", smooth: true, symbol: "none",
      data: [102, 104, 107, 109, 110, 112, 113, 114, 115, 116, 117, 118],
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
      data: [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112],
      lineStyle: { color: "#9CA3AF", width: 1.5, type: "dashed" },
    },
  ],
  legend:  { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
  tooltip: { trigger: "axis" },
}

const topCotistasOption: EChartsOption = {
  grid: { top: 8, right: 24, bottom: 8, left: 110 },
  xAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
  yAxis: {
    type: "category",
    data: ["Outros", "Polaris FO", "Atlas Inv.", "Helios Asset", "Vanguard FII", "Aurora Capital"],
    axisTick: { show: false },
  },
  series: [
    {
      type: "bar", barMaxWidth: 18,
      data: [
        { value: 12, itemStyle: { color: "#9CA3AF",       borderRadius: [0, 3, 3, 0] } },
        { value: 8,  itemStyle: { color: CHART_COLORS[5], borderRadius: [0, 3, 3, 0] } },
        { value: 8,  itemStyle: { color: CHART_COLORS[4], borderRadius: [0, 3, 3, 0] } },
        { value: 10, itemStyle: { color: CHART_COLORS[3], borderRadius: [0, 3, 3, 0] } },
        { value: 22, itemStyle: { color: CHART_COLORS[2], borderRadius: [0, 3, 3, 0] } },
        { value: 40, itemStyle: { color: CHART_COLORS[0], borderRadius: [0, 3, 3, 0] } },
      ],
    },
  ],
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: "{b}: {c}%" },
}

// ───────────────────────────────────────────────────────────────────────────
// Sparklines (mock)
// ───────────────────────────────────────────────────────────────────────────

const SPARK_PL_SUB   = [14.8, 15.2, 15.6, 15.9, 16.2, 16.5, 16.8, 17.1, 17.4, 17.9, 18.3, 18.7]
const SPARK_SUBORD   = [13.8, 14.0, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 14.9, 15.0]
const SPARK_RENT_SUB = [102, 104, 107, 109, 110, 112, 113, 114, 115, 116, 117, 118]
const SPARK_COTISTAS = [9, 9, 10, 10, 10, 11, 11, 11, 11, 12, 12, 12]
const SPARK_RESGATES = [1, 0, 2, 1, 2, 1, 2, 1, 2, 3, 2, 3]

// ───────────────────────────────────────────────────────────────────────────
// labelForStatus — mapeia StatusKey canonico para o rotulo do filtro inline
// ───────────────────────────────────────────────────────────────────────────

const STATUS_LABEL: Record<StatusKey, string> = {
  "em-dia":       "Em dia",
  "liquidado":    "Liquidado",
  "atrasado-30":  "Atrasado",
  "atrasado-60":  "Atrasado",
  "inadimplente": "Inadimplente",
  "recomprado":   "Liquidado",
}

function labelForStatus(s: StatusKey): string {
  return STATUS_LABEL[s] ?? "Em dia"
}

// ───────────────────────────────────────────────────────────────────────────
// AddFilterMenu — Popover de "Mais filtros" (lista dimensoes disponiveis)
// ───────────────────────────────────────────────────────────────────────────

function AddFilterMenu({
  available,
  onAdd,
}: {
  available: DynamicFilterKey[]
  onAdd:     (k: DynamicFilterKey) => void
}) {
  const [open, setOpen] = React.useState(false)
  if (available.length === 0) return null

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cx(
            "inline-flex h-[30px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-[4px] border px-2.5 text-[13px] transition-colors duration-100",
            "border-gray-200 bg-white hover:bg-gray-50",
            "dark:border-gray-800 dark:bg-gray-950 dark:hover:bg-gray-900",
            focusRing,
          )}
        >
          <RiEqualizerLine className="size-3.5 shrink-0 text-gray-500 dark:text-gray-400" aria-hidden="true" />
          <span className="font-medium text-gray-900 dark:text-gray-50">Mais filtros</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className="min-w-44 p-1">
        <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
          Dimensao
        </p>
        {available.map((dim) => (
          <button
            key={dim}
            type="button"
            onClick={() => { setOpen(false); onAdd(dim) }}
            className={cx(
              "block w-full rounded px-2 py-1.5 text-left text-sm transition-colors",
              "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
              focusRing,
            )}
          >
            {dim}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  )
}

// VizParam (chip group de período curto) — agora vem de
// `@/design-system/components/VizParam`. Mantido import abaixo.

// ───────────────────────────────────────────────────────────────────────────
// Variacao diaria — componentes da analise
// ───────────────────────────────────────────────────────────────────────────

// (Helpers de formatacao migraram para BalanceTable._components quando aplicavel.)
// (deprecated VariacaoDiariaSection helpers removed — substituido por BalanceTable)

// ───────────────────────────────────────────────────────────────────────────
// Diario
// ───────────────────────────────────────────────────────────────────────────

function DiarioTab({
  rows,
  tableStatus,
  setTableStatus,
  tableCotista,
  setTableCotista,
  onRowClick,
  balanceRows,
  balanceData,
  balanceDataAnterior,
  balanceEmptyMessage,
  variacoes,
  variacoesLoading,
  variacoesError,
}: {
  rows:                 MovimentacaoRow[]
  tableStatus:          string
  setTableStatus:       (v: string) => void
  tableCotista:         string
  setTableCotista:      (v: string) => void
  onRowClick:           (row: MovimentacaoRow) => void
  balanceRows:          BalanceRow[]
  balanceData?:         string
  balanceDataAnterior?: string
  balanceEmptyMessage?: string
  variacoes:            VariacoesDiaResponse | undefined
  variacoesLoading:     boolean
  variacoesError:       Error | null
}) {
  const [plPeriod, setPlPeriod] = React.useState("12M")
  const [subPeriod, setSubPeriod] = React.useState("12M")
  // Permite ao usuario dispensar o painel de analise IA pra ganhar espaco
  // visual quando estiver focado nos dados. Reload restaura — sem persistencia.
  const [insightsDismissed, setInsightsDismissed] = React.useState(false)

  return (
    <div className="flex flex-col gap-6">
      {/* Insights IA — alinhado com handoff bi-padrao (acima de tudo na aba) */}
      {!insightsDismissed && (
        <InsightBar onDismiss={() => setInsightsDismissed(true)}>
          {MOCK_INSIGHTS.map((ins, i) => (
            <Insight key={i} tone="violet" text={ins.text} />
          ))}
        </InsightBar>
      )}

      {/* Balanço · ótica Sub Jr (data-driven via /controladoria/cota-sub/balanco) */}
      <BalanceTable
        rows={balanceRows}
        data={balanceData}
        dataAnterior={balanceDataAnterior}
        emptyMessage={balanceEmptyMessage}
      />

      {/* Pagamentos do Dia — saidas de caixa em D0 (silver: wh_movimento_caixa) */}
      <PagamentosDiaPanel
        variacoes={variacoes}
        loading={variacoesLoading}
        error={variacoesError}
      />

      {/* Hero 2/3 + 1/3 */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <EChartsCard
          title="Evolucao do PL Cota Sub"
          caption="Patrimonio liquido subordinado · Bitfin"
          option={plCotaSubOption}
          height={160}
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
          title="Distribuicao por classe"
          caption="Mezanino · Junior · participacao %"
          option={distribClasseOption}
          height={100}
          footer={
            <div className="flex items-end justify-between pt-2">
              <div>
                <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  Mezanino
                </div>
                <div className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                  68%
                </div>
              </div>
              <div>
                <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  Junior
                </div>
                <div className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                  32%
                </div>
              </div>
            </div>
          }
        />
      </div>

      {/* Grid 3 colunas */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <EChartsCard
          title="Subscricao vs Resgate"
          caption="Movimentacoes mensais (R$ mi)"
          option={subscRescOption}
          height={160}
          actions={
            <VizParam
              options={["12M", "6M", "3M"]}
              value={subPeriod}
              onChange={setSubPeriod}
            />
          }
        />
        <EChartsCard
          title="Rentabilidade Sub vs CDI"
          caption="Base 100 · mai/25"
          option={rentabSubOption}
          height={160}
        />
        <EChartsCard
          title="Top cotistas subordinados"
          caption="Top 5 + Outros · participacao %"
          option={topCotistasOption}
          height={160}
        />
      </div>

      {/* Tabela */}
      <div className="rounded border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 px-4 py-2.5 dark:border-gray-800">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            Movimentacoes recentes
          </h3>
          <span className="rounded-full border border-gray-200 bg-gray-50 px-1.5 text-[11px] text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
            {rows.length}
          </span>

          {/* Filtros inline da tabela (Status / Cotista) */}
          <div className="ml-2 flex items-center gap-1.5">
            <FilterChip
              label="Status"
              value={tableStatus}
              active={tableStatus !== "Todos"}
            >
              <div className="py-1">
                {TABLE_STATUS_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setTableStatus(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      tableStatus === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {tableStatus === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            <FilterChip
              label="Cotista"
              value={tableCotista}
              active={tableCotista !== "Todos"}
            >
              <div className="py-1">
                {TABLE_COTISTA_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setTableCotista(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      tableCotista === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {tableCotista === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>
          </div>

          <Button variant="ghost" className="ml-auto">
            <RiDownloadLine className="size-3.5" aria-hidden="true" />
            Exportar
          </Button>
        </div>
        <DataTable
          data={rows}
          columns={MOVIMENTACOES_COLUMNS}
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

const col = createColumnHelper<MovimentacaoRow>()

const MOVIMENTACOES_COLUMNS: ColumnDef<MovimentacaoRow, unknown>[] = [
  col.accessor("id", {
    header: "ID",
    size:   150,
    cell:   (info) => <IdCell value={info.getValue<string>()} />,
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("cotista", {
    header: "Cotista",
    size:   180,
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("classe", {
    header: "Classe",
    size:   110,
    cell:   (info) => (
      <span className="text-sm text-gray-500 dark:text-gray-400">
        {info.getValue<string>()}
      </span>
    ),
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("tipo", {
    header: "Tipo",
    size:   110,
    cell:   (info) => {
      const tipo  = info.getValue<MovimentacaoTipo>()
      const isSub = tipo === "subscricao"
      return (
        <span className={cx(
          "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
          isSub
            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
            : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
        )}>
          {isSub ? "Subscricao" : "Resgate"}
        </span>
      )
    },
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("valor", {
    header: "Valor",
    size:   140,
    cell:   (info) => <CurrencyCell value={info.getValue<number>()} />,
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("data", {
    header: "Data",
    size:   110,
    cell:   (info) => <DateCell value={info.getValue<string>()} />,
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("status", {
    header: "Status",
    size:   140,
    cell:   (info) => <StatusCell value={info.getValue<StatusKey>()} />,
  }) as ColumnDef<MovimentacaoRow, unknown>,
]

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

export default function CotaSubPage() {
  const [search, setSearch] = React.useState("")
  // Dia: tab "Diario" analisa um unico dia por vez. Default = hoje.
  const today = React.useMemo(() => new Date(), [])
  const [day, setDay] = React.useState<Date>(today)
  // Fundo: opcoes vem de Cadastros · UAs do tipo FIDC. "Todos" e a opcao implicita default.
  const fundosQuery = useUAs({ tipo: "fidc", ativa: true })
  const fundoOptions = React.useMemo(
    () => ["Todos", ...(fundosQuery.data?.map((ua) => ua.nome) ?? [])],
    [fundosQuery.data],
  )
  const [fundo,  setFundo]  = React.useState<string>("Todos")
  const [classe, setClasse] = React.useState<ClasseOption>("Todas")

  // Filtros dinamicos (adicionados via "Mais filtros") — array imutavel no
  // sentido do user: cada chip vira RemovableChip + dropdown FilterChip.
  const [dynamicFilters, setDynamicFilters] = React.useState<DynamicFilter[]>([])

  // Filtros inline da DataTable (escopo: tabela apenas, nao charts)
  const [tableStatus,  setTableStatus]  = React.useState<string>("Todos")
  const [tableCotista, setTableCotista] = React.useState<string>("Todos")

  const [activeTab, setActiveTab] = React.useState<TabKey>("diario")

  // Atalhos Cmd/Ctrl + 1..3 para tabs (regra L3 do CLAUDE.md §11.6).
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

  const ai = useAIPanel()

  const [selected, setSelected] = React.useState<MovimentacaoRow | null>(null)

  // Lookup do UUID da UA selecionada (para o endpoint backend que exige fundo_id).
  const fundoId = React.useMemo(() => {
    if (fundo === "Todos") return null
    return fundosQuery.data?.find((ua) => ua.nome === fundo)?.id ?? null
  }, [fundo, fundosQuery.data])

  const dayIso = React.useMemo(() => format(day, "yyyy-MM-dd"), [day])
  const balanceQuery   = useBalanco(fundoId, dayIso)
  const variacoesQuery = useVariacoesDia(fundoId, dayIso)
  // Pagina requer fundo selecionado. Sem fundo, Z4 entra em EmptyState.
  const fundoSelecionado = fundoId !== null

  const aiContext = React.useMemo(
    () => ({
      page: "Controladoria · Cota Sub",
      period: format(day, "dd/MM/yyyy"),
      filters: [
        fundo  !== "Todos" && `Fundo: ${fundo}`,
        classe !== "Todas" && `Classe: ${classe}`,
        ...dynamicFilters.map((f) => `${f.key}: ${f.value}`),
        search             && `Busca: ${search}`,
      ].filter(Boolean).join(", ") || "Nenhum",
    }),
    [day, fundo, classe, dynamicFilters, search],
  )

  const handleShare = React.useCallback(() => {
    void navigator.clipboard?.writeText(window.location.href)
  }, [])

  const handleExport = React.useCallback(() => {
    // Stub — wire to real export endpoint (CSV/XLSX da pagina inteira).
    // eslint-disable-next-line no-console
    console.log("export pagina cota-sub", { day, fundo, classe, dynamicFilters })
  }, [day, fundo, classe, dynamicFilters])

  // Linhas filtradas da DataTable (escopo: filtros inline da tabela)
  const filteredRows = React.useMemo(
    () => MOCK_MOVIMENTACOES.filter((r) => {
      if (tableStatus !== "Todos" && labelForStatus(r.status) !== tableStatus) return false
      if (tableCotista !== "Todos" && r.cotista !== tableCotista) return false
      if (search && !r.cotista.toLowerCase().includes(search.toLowerCase()) && !r.id.toLowerCase().includes(search.toLowerCase())) return false
      return true
    }),
    [tableStatus, tableCotista, search],
  )

  // Adicionar / remover filtro dinamico
  const addDynamicFilter = React.useCallback((key: DynamicFilterKey) => {
    setDynamicFilters((curr) => {
      if (curr.some((f) => f.key === key)) return curr
      const opts = DYNAMIC_FILTER_OPTIONS[key]
      return [...curr, { key, value: opts[0] }]
    })
  }, [])
  const removeDynamicFilter = React.useCallback((key: DynamicFilterKey) => {
    setDynamicFilters((curr) => curr.filter((f) => f.key !== key))
  }, [])
  const setDynamicFilterValue = React.useCallback((key: DynamicFilterKey, value: string) => {
    setDynamicFilters((curr) => curr.map((f) => f.key === key ? { ...f, value } : f))
  }, [])

  const usedDynamicKeys = dynamicFilters.map((f) => f.key)
  const availableDynamicKeys = (Object.keys(DYNAMIC_FILTER_OPTIONS) as DynamicFilterKey[])
    .filter((k) => !usedDynamicKeys.includes(k))

  // Saved views — params atuais + handler
  const currentViewParams = React.useMemo<Record<string, string>>(() => ({
    day:     format(day, "yyyy-MM-dd"),
    fundo,
    classe,
    search,
    ...Object.fromEntries(dynamicFilters.map((f) => [f.key, f.value])),
  }), [day, fundo, classe, search, dynamicFilters])

  const handleApplyView = React.useCallback((view: { params: Record<string, string> }) => {
    const p = view.params
    if (p.fundo)  setFundo(p.fundo)
    if (p.classe) setClasse(p.classe as ClasseOption)
    if (p.search) setSearch(p.search)
    if (p.day) {
      const d = new Date(p.day)
      if (!isNaN(d.getTime())) setDay(d)
    }
    // restaura filtros dinamicos
    const restored: DynamicFilter[] = []
    for (const k of Object.keys(DYNAMIC_FILTER_OPTIONS) as DynamicFilterKey[]) {
      if (p[k]) restored.push({ key: k, value: p[k] as string })
    }
    setDynamicFilters(restored)
  }, [])

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden bg-gray-50 dark:bg-gray-950">
      {/* Coluna principal */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">

        {/* Z1 — PageHeader */}
        <div className="shrink-0 px-6 pt-5 pb-3">
          <PageHeader
            title="Cota Sub"
            info="Analise da cota subordinada do FIDC: PL, rentabilidade vs CDI, distribuicao por cotista subordinado e fluxo de subscricao/resgate."
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
          <FilterBar
            extraActions={
              <SavedViewsDropdown
                currentParams={currentViewParams}
                onApplyView={handleApplyView}
              />
            }
          >
            <FilterSearch
              placeholder="Buscar cotistas..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onClear={() => setSearch("")}
            />

            <FilterChip
              label="Dia"
              value={isSameDay(day, today) ? "Hoje" : format(day, "dd/MM/yyyy")}
              active={!isSameDay(day, today)}
              icon={RiCalendarLine}
            >
              <Calendar
                mode="single"
                selected={day}
                onSelect={(d) => d && setDay(d)}
                locale={ptBR}
                disabled={{ after: today }}
                initialFocus
              />
            </FilterChip>

            <FilterChip
              label="Fundo"
              value={fundo}
              active={fundo !== "Todos"}
            >
              <div className="py-1">
                {fundosQuery.isLoading && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Carregando UAs...
                  </div>
                )}
                {fundosQuery.isError && (
                  <div className="px-3 py-1.5 text-xs text-red-600 dark:text-red-400">
                    Falha ao carregar UAs
                  </div>
                )}
                {!fundosQuery.isLoading && !fundosQuery.isError && fundoOptions.length === 1 && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Nenhuma UA do tipo FIDC cadastrada
                  </div>
                )}
                {fundoOptions.map((opt) => (
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
              label="Classe"
              value={classe}
              active={classe !== "Todas"}
            >
              <div className="py-1">
                {CLASSE_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setClasse(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      classe === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {classe === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            {/* Filtros dinamicos — adicionados via "Mais filtros" */}
            {dynamicFilters.map((f) => (
              <FilterChip
                key={f.key}
                label={f.key}
                value={f.value}
                active={f.value !== DYNAMIC_FILTER_OPTIONS[f.key][0]}
              >
                <div className="py-1">
                  {DYNAMIC_FILTER_OPTIONS[f.key].map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setDynamicFilterValue(f.key, opt)}
                      className={cx(
                        "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                        f.value === opt
                          ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                          : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                      )}
                    >
                      <span className="flex-1 text-left">{opt}</span>
                      {f.value === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => removeDynamicFilter(f.key)}
                    className={cx(
                      "mt-1 flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      "text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10",
                    )}
                  >
                    Remover filtro
                  </button>
                </div>
              </FilterChip>
            ))}

            {search && (
              <RemovableChip
                label="Busca"
                value={search}
                onRemove={() => setSearch("")}
              />
            )}

            <AddFilterMenu
              available={availableDynamicKeys}
              onAdd={addDynamicFilter}
            />
          </FilterBar>
        </div>

        {/* Z4 — Conteudo da aba */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {!fundoSelecionado ? (
            <EmptyState
              icon={RiFundsLine}
              title="Selecione um fundo para comecar"
              description='A pagina Cota Sub analisa um FIDC por vez. Escolha o fundo no filtro "Fundo" acima para carregar PL, rentabilidade, decomposicao da variacao diaria e movimentacoes.'
              className="mt-4"
            />
          ) : (
            <div className="flex flex-col gap-4">
              <KpiStrip>
                <KpiCard
                  label="PL da Cota Sub"
                  deltaSub="vs mes anterior"
                  value="R$ 18,7M"
                  delta={{ value: 1.8, suffix: "%" }}
                  sparkData={SPARK_PL_SUB}
                  sparkColor="#059669"
                  source="Bitfin"
                />
                <KpiCard
                  label="Subordinacao efetiva"
                  deltaSub="vs mes anterior"
                  value="15,0%"
                  delta={{ value: 0.3, suffix: "pp" }}
                  sparkData={SPARK_SUBORD}
                  sparkColor="#3B82F6"
                />
                <KpiCard
                  label="Rentab. Sub vs CDI"
                  deltaSub="vs benchmark"
                  value="118,2%"
                  delta={{ value: 4.1, suffix: "pp" }}
                  sparkData={SPARK_RENT_SUB}
                  sparkColor="#3B82F6"
                />
                <KpiCard
                  label="Cotistas subordinados"
                  deltaSub="vs mes anterior"
                  value="12"
                  delta={{ value: 1, suffix: "" }}
                  sparkData={SPARK_COTISTAS}
                  sparkColor="#6B7280"
                />
                <KpiCard
                  label="Resgates"
                  deltaSub="vs semana anterior"
                  value="3"
                  currentValue={3}
                  delta={{ value: 1, suffix: "", direction: "up", good: false }}
                  alertThreshold={{ value: 2, severity: "warn" }}
                  sparkData={SPARK_RESGATES}
                  sparkColor="#F59E0B"
                  intensity={{ tone: "neg", level: "mid" }}
                />
              </KpiStrip>

              {activeTab === "diario" && (
                <DiarioTab
                  rows={filteredRows}
                  tableStatus={tableStatus}
                  setTableStatus={setTableStatus}
                  tableCotista={tableCotista}
                  setTableCotista={setTableCotista}
                  onRowClick={setSelected}
                  balanceRows={balanceQuery.data?.rows ?? []}
                  balanceData={balanceQuery.data?.data}
                  balanceDataAnterior={balanceQuery.data?.data_anterior}
                  balanceEmptyMessage={
                    balanceQuery.isLoading
                      ? "Carregando..."
                      : balanceQuery.isError
                      ? `Erro: ${(balanceQuery.error as Error)?.message ?? "desconhecido"}`
                      : undefined
                  }
                  variacoes={variacoesQuery.data}
                  variacoesLoading={variacoesQuery.isLoading}
                  variacoesError={variacoesQuery.error as Error | null}
                />
              )}
              {activeTab === "evolucao" && <PlaceholderTab label="Evolucao" />}
              {activeTab === "cotistas" && <PlaceholderTab label="Cotistas" />}
            </div>
          )}
        </div>

        {/* Z5 — ProvenanceFooter (mock) */}
        <ProvenanceFooter sources={MOCK_PROVENANCE} />
      </div>

      {/* AI Panel */}
      <AIPanel
        open={ai.open}
        onClose={() => ai.setOpen(false)}
        context={aiContext}
        insights={MOCK_INSIGHTS}
      />

      {/* DrillDown */}
      <DrillDownSheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.id ?? "Movimentacao"}
      >
        {selected && (
          <>
            <DrillDownSheet.Header
              breadcrumb={["Cota Sub", selected.id]}
              statusSlot={
                <span className={cx(
                  "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
                  selected.tipo === "subscricao"
                    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                    : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
                )}>
                  {selected.tipo === "subscricao" ? "Subscricao" : "Resgate"}
                </span>
              }
            />
            <DrillDownSheet.Hero
              id={selected.id}
              title={selected.cotista}
              value={selected.valor}
              delta={{ value: selected.tipo === "subscricao" ? 1.8 : -0.6, label: "vs ultima movimentacao" }}
            />
            <DrillDownSheet.Tabs
              tabs={[
                {
                  value:   "geral",
                  label:   "Visao geral",
                  content: (
                    <>
                      <DrillDownSheet.PropertyList
                        items={[
                          { label: "Cotista",      value: selected.cotista },
                          { label: "Classe",       value: selected.classe },
                          { label: "Tipo",         value: selected.tipo === "subscricao" ? "Subscricao" : "Resgate" },
                          { label: "Valor",        value: selected.valor, type: "currency" },
                          { label: "Data",         value: selected.data, type: "date" },
                          { label: "Status",       value: STATUS_LABEL[selected.status] },
                          { label: "Origem",       value: "QiTech" },
                          { label: "Liquidacao",   value: selected.status === "liquidado" ? "D+0" : "D+1 (estimada)" },
                        ]}
                      />
                      <div className="mt-6">
                        <DrillDownSheet.SectionLabel>Linha do tempo</DrillDownSheet.SectionLabel>
                        <DrillDownSheet.Timeline
                          events={buildTimeline(selected)}
                        />
                      </div>
                    </>
                  ),
                },
                { value: "historico",  label: "Historico",   content: <PlaceholderSheetTab label="Historico" /> },
                { value: "documentos", label: "Documentos",  content: <PlaceholderSheetTab label="Documentos" /> },
                { value: "atividade",  label: "Atividade",   content: <PlaceholderSheetTab label="Atividade" /> },
              ]}
              defaultValue="geral"
            />
            <DrillDownSheet.Footer>
              <Button variant="secondary">Exportar PDF</Button>
              <Button variant="secondary">Ver historico</Button>
              <div className="flex-1" />
              <Button variant="primary">Registrar evento</Button>
            </DrillDownSheet.Footer>
          </>
        )}
      </DrillDownSheet>

    </div>
  )
}

function PlaceholderSheetTab({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center py-10 text-sm text-gray-500 dark:text-gray-400">
      Em desenvolvimento — aba &quot;{label}&quot;
    </div>
  )
}

function buildTimeline(row: MovimentacaoRow): TimelineEventDef[] {
  const baseDate = format(new Date(row.data), "dd/MM/yyyy")
  const events: TimelineEventDef[] = [
    { type: "cedida",    date: baseDate, actor: "Front-office",  description: `${row.tipo === "subscricao" ? "Subscricao" : "Resgate"} solicitada pelo cotista` },
    { type: "lastreada", date: baseDate, actor: "Back-office",   description: "Pedido validado e enviado a administradora" },
  ]
  if (row.status === "liquidado") {
    events.push({ type: "liquidada", date: baseDate, actor: "QiTech", description: "Liquidacao efetivada", current: true })
  } else if (row.status === "atrasado-30" || row.status === "atrasado-60") {
    events.push({ type: "atrasada", date: baseDate, actor: "Sistema", description: "Aguardando confirmacao do cotista", current: true })
  } else {
    events.push({ type: "a-vencer", date: "—", actor: "Sistema", description: "Aguardando liquidacao", current: true })
  }
  return events
}
