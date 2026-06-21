// Aba Players — ranking de administradoras (top-25 por PL).

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import type { EChartsOption } from "echarts"
import type { ColumnDef } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { DataTable } from "@/design-system/components/DataTable"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import { tableTokens } from "@/design-system/tokens/table"
import { cardTokens } from "@/design-system/tokens/card"
import { biPanorama } from "@/lib/api-client"
import type { PanoramaAdminRankingItem, PanoramaFilters } from "@/lib/api-client"

import { fmtBRLCompact, fmtInt, fmtPct } from "./format"
import { TabSkeleton, TabError } from "./_state"

type PlayerRow = PanoramaAdminRankingItem & { rank: number }

export function PlayersTab({ filters }: { filters: PanoramaFilters }) {
  const q = useQuery({
    queryKey: ["bi", "panorama", "players", filters],
    queryFn: () => biPanorama.players(filters),
  })

  if (q.isLoading) return <TabSkeleton />
  if (q.isError || !q.data) return <TabError onRetry={() => q.refetch()} />

  const { ranking } = q.data.data
  const rows: PlayerRow[] = ranking.map((r, i) => ({ ...r, rank: i + 1 }))

  // Scatter: nº de fundos (x) × PL médio em R$ mi (y), bolha = PL total.
  const scatterOption: EChartsOption = {
    grid: { top: 16, right: 20, bottom: 40, left: 56 },
    xAxis: {
      type: "value",
      name: "Nº de fundos",
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { fontSize: 11, color: "#6B7280" },
      axisLabel: { fontSize: 11, color: "#6B7280" },
      splitLine: { lineStyle: { color: "rgba(107,114,128,0.15)" } },
    },
    yAxis: {
      type: "value",
      name: "PL médio (R$ mi)",
      nameTextStyle: { fontSize: 11, color: "#6B7280" },
      axisLabel: { fontSize: 11, color: "#6B7280", formatter: (v: number) => fmtInt.format(v) },
      splitLine: { lineStyle: { color: "rgba(107,114,128,0.15)" } },
    },
    series: [
      {
        type: "scatter",
        symbolSize: (d: number[]) => Math.max(8, Math.sqrt(d[2]) / 90),
        data: ranking.map((r) => [r.qtd, r.pl_medio / 1e6, r.pl, r.admin]),
        itemStyle: { color: "#3B82F6", opacity: 0.6 },
      },
    ],
    tooltip: {
      trigger: "item",
      formatter: (p: unknown) => {
        const d = (p as { data: [number, number, number, string] }).data
        return `${d[3]}<br/>${fmtInt.format(d[0])} fundos · PL médio ${fmtBRLCompact(d[1] * 1e6)}<br/>PL total ${fmtBRLCompact(d[2])}`
      },
    },
  }

  return (
    <>
      <EChartsCard
        title="ADMINISTRADORAS · Nº DE FUNDOS × PL MÉDIO"
        caption="Cada bolha = uma administradora (tamanho = PL total). Esquerda/alto = poucos fundos grandes; direita/baixo = muitos fundos pequenos."
        option={scatterOption}
        height={260}
      />

      <Card className={cx(cardTokens.body, "overflow-x-auto")}>
        <DataTable
          data={rows}
          columns={PLAYER_COLUMNS}
          showDensityToggle={false}
          showColumnManager={false}
        />
      </Card>
    </>
  )
}

const PLAYER_COLUMNS: ColumnDef<PlayerRow, unknown>[] = [
  {
    id: "rank",
    header: "#",
    accessorFn: (r) => r.rank,
    cell: ({ row }) => (
      <span className={tableTokens.cellNumberSecondary}>{row.original.rank}</span>
    ),
  },
  {
    id: "admin",
    header: "Administradora",
    accessorFn: (r) => r.admin,
    cell: ({ row }) => (
      <span
        className={cx(tableTokens.cellText, "block max-w-[280px] truncate")}
        title={row.original.admin}
      >
        {row.original.admin}
      </span>
    ),
  },
  {
    id: "qtd",
    header: "Qtd",
    accessorFn: (r) => r.qtd,
    meta: { align: "right" },
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumber, "block text-right")}>
        {fmtInt.format(row.original.qtd)}
      </span>
    ),
  },
  {
    id: "pct_qtd",
    header: "% qtd",
    accessorFn: (r) => r.pct_qtd,
    meta: { align: "right" },
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumberSecondary, "block text-right")}>
        {fmtPct(row.original.pct_qtd, 1)}
      </span>
    ),
  },
  {
    id: "pl",
    header: "PL",
    accessorFn: (r) => r.pl,
    meta: { align: "right" },
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumber, "block text-right")}>
        {fmtBRLCompact(row.original.pl)}
      </span>
    ),
  },
  {
    id: "pct_pl",
    header: "% PL",
    accessorFn: (r) => r.pct_pl,
    meta: { align: "right" },
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumberSecondary, "block text-right")}>
        {fmtPct(row.original.pct_pl, 1)}
      </span>
    ),
  },
  {
    id: "pl_medio",
    header: "PL médio",
    accessorFn: (r) => r.pl_medio,
    meta: { align: "right" },
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumber, "block text-right")}>
        {fmtBRLCompact(row.original.pl_medio)}
      </span>
    ),
  },
  {
    id: "pl_mediano",
    header: "PL mediano",
    accessorFn: (r) => r.pl_mediano,
    meta: { align: "right" },
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumber, "block text-right")}>
        {fmtBRLCompact(row.original.pl_mediano)}
      </span>
    ),
  },
  {
    id: "liquidez",
    header: "Liquidez",
    accessorFn: (r) => r.liquidez_pct,
    meta: { align: "right" },
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumber, "block text-right")}>
        {fmtPct(row.original.liquidez_pct, 1)}
      </span>
    ),
  },
]
