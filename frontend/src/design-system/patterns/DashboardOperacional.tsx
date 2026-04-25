// src/design-system/patterns/DashboardOperacional.tsx
//
// PATTERN — Dashboard Operacional
// Copy, paste, adapt. Not a black-box component.
//
// Composes:
//   PageHeader → FilterBar → KpiStrip (4 KPIs canônicos) →
//   Grid 2×2 EChartsCards → DataTable de atividade recente
//
// Use for: /bi/operacoes, /bi/carteira, /bi/rentabilidade
//
// HOW TO ADAPT:
//   1. Replace SAMPLE_KPI_* with your real data from useQuery.
//   2. Swap ECharts options for your series.
//   3. Replace RECENT_ACTIVITY columns/data with your domain type.
//   4. Remove KPI cards or chart panels that don't apply.

"use client"

import * as React from "react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { RiCalendarLine, RiArrowRightLine } from "@remixicon/react"

import { KpiCard, KpiStrip, FIDC_KPI_META } from "@/design-system/components/KpiStrip"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import { FilterBar, FilterChip } from "@/design-system/components/FilterBar"
import {
  DataTable,
  CurrencyCell,
  DateCell,
  StatusCell,
} from "@/design-system/components/DataTable"
import { Button } from "@/components/tremor/Button"
import type { StatusKey } from "@/design-system/tokens"
import { tokens } from "@/design-system/tokens"

const SPARK_PL    = [100, 108, 104, 112, 118, 115, 122, 120, 124, 125]
const SPARK_RENT  = [108, 109, 110, 112, 111, 113, 112, 114, 115, 112]
const SPARK_INAD  = [2.8, 2.9, 3.0, 2.9, 3.1, 3.0, 3.1, 3.2, 3.1, 3.2]
const SPARK_PDD   = [1.8, 1.9, 2.0, 2.0, 2.1, 2.0, 2.1, 2.1, 2.0, 2.1]

const CHART_COLORS = tokens.colors.chart

const volumeOption = {
  grid: { top: 16, right: 8, bottom: 32, left: 56 },
  xAxis: {
    type: "category" as const,
    data: ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"],
    axisLabel: { fontSize: 11 },
  },
  yAxis: { type: "value" as const, axisLabel: { fontSize: 11 } },
  series: [
    {
      name: "Em dia", type: "bar" as const, stack: "total",
      data: [420, 432, 401, 454, 590, 530, 610, 640, 680, 710, 750, 820],
      itemStyle: { color: CHART_COLORS[3] },
    },
    {
      name: "Atrasado", type: "bar" as const, stack: "total",
      data: [40, 52, 61, 34, 90, 30, 60, 44, 68, 55, 70, 82],
      itemStyle: { color: CHART_COLORS[4] },
    },
    {
      name: "Inadimplente", type: "bar" as const, stack: "total",
      data: [10, 12, 8, 14, 20, 10, 18, 12, 22, 18, 15, 20],
      itemStyle: { color: CHART_COLORS[5] },
    },
  ],
  tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
  legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
}

const inadimplenciaOption = {
  grid: { top: 12, right: 12, bottom: 32, left: 48 },
  xAxis: { type: "category" as const, data: ["1-30d", "31-60d", "61-90d", "91-120d", "120d+"] },
  yAxis: { type: "value" as const, axisLabel: { formatter: "{value}%", fontSize: 11 } },
  series: [
    {
      name: "Abr/26", type: "line" as const,
      data: [1.2, 0.8, 0.6, 1.8, 3.2],
      smooth: true, symbol: "circle", symbolSize: 5,
      itemStyle: { color: CHART_COLORS[5] },
    },
    {
      name: "Mar/26", type: "line" as const,
      data: [1.0, 0.9, 0.7, 1.5, 2.8],
      smooth: true, symbol: "circle", symbolSize: 5,
      lineStyle: { type: "dashed" as const },
      itemStyle: { color: CHART_COLORS[4] },
    },
  ],
  tooltip: { trigger: "axis" as const },
  legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
}

const rentabilidadeOption = {
  grid: { top: 12, right: 12, bottom: 32, left: 48 },
  xAxis: {
    type: "category" as const,
    data: ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun"],
    axisLabel: { fontSize: 11 },
  },
  yAxis: { type: "value" as const, axisLabel: { formatter: "{value}%", fontSize: 11 } },
  series: [
    {
      name: "FIDC Alpha", type: "line" as const,
      data: [102, 104, 107, 109, 111, 112],
      smooth: true, symbol: "none",
      areaStyle: { opacity: 0.08 },
      itemStyle: { color: CHART_COLORS[0] },
    },
    {
      name: "CDI", type: "line" as const,
      data: [100, 101, 102, 103, 104, 105],
      smooth: true, symbol: "none",
      lineStyle: { type: "dashed" as const },
      itemStyle: { color: CHART_COLORS[1] },
    },
  ],
  tooltip: { trigger: "axis" as const },
  legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
}

const distribuicaoOption = {
  tooltip: { trigger: "item" as const },
  legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
  series: [{
    type: "pie" as const,
    radius: ["42%", "68%"],
    center: ["50%", "44%"],
    data: [
      { name: "Metalúrgica SP",    value: 185400, itemStyle: { color: CHART_COLORS[0] } },
      { name: "Agro Grãos Sul",    value: 450000, itemStyle: { color: CHART_COLORS[1] } },
      { name: "Tech Soluções",     value: 230000, itemStyle: { color: CHART_COLORS[2] } },
      { name: "Farmacêutica Sul",  value: 215000, itemStyle: { color: CHART_COLORS[3] } },
      { name: "Outros",            value: 156000, itemStyle: { color: CHART_COLORS[4] } },
    ],
    label: { fontSize: 11 },
  }],
}

interface ActivityRow {
  id:      string
  cedente: string
  valor:   number
  date:    string
  status:  StatusKey
}

const RECENT_ACTIVITY: ActivityRow[] = [
  { id: "CCB-001243", cedente: "Confecções RJ",     valor: 143200, date: "2026-04-24", status: "atrasado-30" },
  { id: "CCB-001242", cedente: "Padaria Industrial", valor:  29800, date: "2026-04-23", status: "recomprado" },
  { id: "CCB-001241", cedente: "Farmacêutica Sul",   valor: 215000, date: "2026-04-22", status: "em-dia" },
  { id: "CCB-001240", cedente: "Logística Express",  valor:  67800, date: "2026-04-21", status: "liquidado" },
  { id: "CCB-001239", cedente: "Móveis Rápidos",     valor:  34500, date: "2026-04-20", status: "atrasado-60" },
]

const activityCol = createColumnHelper<ActivityRow>()

const ACTIVITY_COLUMNS: ColumnDef<ActivityRow, unknown>[] = [
  activityCol.accessor("id", {
    header: "CCB",
    size:   140,
    cell:   (info) => (
      <span className="font-mono text-xs tabular-nums text-blue-600 dark:text-blue-400">{info.getValue<string>()}</span>
    ),
  }) as ColumnDef<ActivityRow, unknown>,
  activityCol.accessor("cedente", {
    header: "Cedente",
    cell:   (info) => <span className="text-sm text-gray-900 dark:text-gray-50">{info.getValue<string>()}</span>,
  }) as ColumnDef<ActivityRow, unknown>,
  activityCol.accessor("valor", {
    header: "Valor",
    size:   120,
    cell:   (info) => <div className="text-right"><CurrencyCell value={info.getValue<number>()} /></div>,
  }) as ColumnDef<ActivityRow, unknown>,
  activityCol.accessor("date", {
    header: "Data",
    size:   100,
    cell:   (info) => <DateCell value={info.getValue<string>()} format="relative" />,
  }) as ColumnDef<ActivityRow, unknown>,
  activityCol.accessor("status", {
    header: "Status",
    size:   130,
    cell:   (info) => <StatusCell value={info.getValue<StatusKey>()} />,
  }) as ColumnDef<ActivityRow, unknown>,
]

const PERIODS = ["7 dias", "30 dias", "90 dias", "12 meses", "YTD"] as const
type Period = typeof PERIODS[number]

export function DashboardOperacional() {
  const [period, setPeriod] = React.useState<Period>("30 dias")

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="shrink-0 border-b border-gray-200 dark:border-gray-800 px-6 py-4">
        <p className="mb-0.5 text-xs text-gray-500 dark:text-gray-400">BI</p>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-50">Dashboard</h1>
          <div className="ml-auto flex items-center gap-2">
            <Button variant="secondary">Exportar</Button>
          </div>
        </div>
      </div>

      <FilterBar className="px-6">
        <FilterChip label="Período" value={period} active={period !== "30 dias"}>
          <div className="py-1">
            {PERIODS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPeriod(p)}
                className="flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              >
                <RiCalendarLine className="size-3.5 text-gray-400" aria-hidden="true" />
                <span className="flex-1 text-left">{p}</span>
                {period === p && <span className="size-1.5 rounded-full bg-blue-500" />}
              </button>
            ))}
          </div>
        </FilterChip>
        <FilterChip label="Módulo" value="BI" />
        <FilterChip label="Produto" value="Todos" />
      </FilterBar>

      <div className="flex-1 overflow-y-auto">
        <div className="flex flex-col gap-5 p-6">
          <section aria-label="KPIs principais">
            <div className="rounded border border-gray-200 dark:border-gray-900 bg-white dark:bg-[#090E1A] px-5 py-4 shadow-xs">
              <KpiStrip>
                <KpiCard
                  {...FIDC_KPI_META.pl}
                  value="R$ 124,5M"
                  sub="abr/26"
                  delta={{ value: 2.34, suffix: "%" }}
                  sparkData={SPARK_PL}
                  sparkColor="#059669"
                  variant="default"
                />
                <KpiCard
                  {...FIDC_KPI_META.rentabilidade}
                  value="112,4%"
                  delta={{ value: 3.1, suffix: "pp" }}
                  sparkData={SPARK_RENT}
                  sparkColor="#3B82F6"
                  variant="default"
                />
                <KpiCard
                  {...FIDC_KPI_META.inadimplencia}
                  value="3,2%"
                  delta={{ value: 0.4, suffix: "pp", direction: "up", good: false }}
                  sparkData={SPARK_INAD}
                  sparkColor="#DC2626"
                  variant="default"
                />
                <KpiCard
                  {...FIDC_KPI_META.pdd}
                  value="R$ 2,1M"
                  delta={{ value: -5.2, suffix: "%", direction: "down", good: true }}
                  sparkData={SPARK_PDD}
                  sparkColor="#D97706"
                  variant="default"
                />
              </KpiStrip>
            </div>
          </section>

          <section aria-label="Análises" className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <EChartsCard
              title="Volume de Cessões"
              caption={`Por status — ${period}`}
              option={volumeOption}
              height={220}
              actions={
                <Button variant="ghost">
                  Ver detalhes <RiArrowRightLine className="size-3" aria-hidden="true" />
                </Button>
              }
            />
            <EChartsCard
              title="Inadimplência por Prazo"
              caption="Comparativo mês atual vs anterior"
              option={inadimplenciaOption}
              height={220}
            />
            <EChartsCard
              title="Rentabilidade Acumulada"
              caption="FIDC Alpha vs CDI — últimos 6 meses"
              option={rentabilidadeOption}
              height={220}
            />
            <EChartsCard
              title="Distribuição por Cedente"
              caption="Top 5 cedentes por valor"
              option={distribuicaoOption}
              height={220}
            />
          </section>

          <section aria-label="Atividade recente">
            <div className="rounded border border-gray-200 dark:border-gray-900 bg-white dark:bg-[#090E1A] shadow-xs overflow-hidden">
              <div className="flex items-center justify-between border-b border-gray-100 dark:border-gray-900 px-4 py-3">
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">Atividade recente</h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Últimas movimentações na carteira</p>
                </div>
                <Button variant="ghost">
                  Ver todas <RiArrowRightLine className="size-3" aria-hidden="true" />
                </Button>
              </div>
              <DataTable
                data={RECENT_ACTIVITY}
                columns={ACTIVITY_COLUMNS}
                density="compact"
                showDensityToggle={false}
                showColumnManager={false}
                showExport={false}
                virtualize={false}
              />
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
