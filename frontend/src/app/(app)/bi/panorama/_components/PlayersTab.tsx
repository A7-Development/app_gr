// Aba Players — ranking de administradoras (top-25 por PL).

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import type { EChartsOption } from "echarts"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import { tableTokens } from "@/design-system/tokens/table"
import { cardTokens } from "@/design-system/tokens/card"
import { biPanorama } from "@/lib/api-client"
import type { PanoramaFilters } from "@/lib/api-client"

import { fmtBRLCompact, fmtInt, fmtPct } from "./format"
import { TabSkeleton, TabError } from "./_state"

export function PlayersTab({ filters }: { filters: PanoramaFilters }) {
  const q = useQuery({
    queryKey: ["bi", "panorama", "players", filters],
    queryFn: () => biPanorama.players(filters),
  })

  if (q.isLoading) return <TabSkeleton />
  if (q.isError || !q.data) return <TabError onRetry={() => q.refetch()} />

  const { ranking } = q.data.data

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
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-800">
              <th className={cx(tableTokens.header, "py-2 pr-2 text-left text-gray-500 dark:text-gray-400")}>#</th>
              <th className={cx(tableTokens.header, "py-2 pr-3 text-left text-gray-500 dark:text-gray-400")}>Administradora</th>
              <th className={cx(tableTokens.header, "py-2 px-2 text-right text-gray-500 dark:text-gray-400")}>Qtd</th>
              <th className={cx(tableTokens.header, "py-2 px-2 text-right text-gray-500 dark:text-gray-400")}>% qtd</th>
              <th className={cx(tableTokens.header, "py-2 px-2 text-right text-gray-500 dark:text-gray-400")}>PL</th>
              <th className={cx(tableTokens.header, "py-2 px-2 text-right text-gray-500 dark:text-gray-400")}>% PL</th>
              <th className={cx(tableTokens.header, "py-2 px-2 text-right text-gray-500 dark:text-gray-400")}>PL médio</th>
              <th className={cx(tableTokens.header, "py-2 px-2 text-right text-gray-500 dark:text-gray-400")}>PL mediano</th>
              <th className={cx(tableTokens.header, "py-2 pl-2 text-right text-gray-500 dark:text-gray-400")}>Liquidez</th>
            </tr>
          </thead>
          <tbody>
            {ranking.map((r, i) => (
              <tr
                key={r.cnpj_admin}
                className="border-b border-gray-100 dark:border-gray-900 hover:bg-gray-50 dark:hover:bg-gray-900/40"
              >
                <td className={cx(tableTokens.cellNumberSecondary, "py-1.5 pr-2")}>{i + 1}</td>
                <td className={cx(tableTokens.cellText, "py-1.5 pr-3 max-w-[280px] truncate")} title={r.admin}>
                  {r.admin}
                </td>
                <td className={cx(tableTokens.cellNumber, "py-1.5 px-2 text-right")}>{fmtInt.format(r.qtd)}</td>
                <td className={cx(tableTokens.cellNumberSecondary, "py-1.5 px-2 text-right")}>{fmtPct(r.pct_qtd, 1)}</td>
                <td className={cx(tableTokens.cellNumber, "py-1.5 px-2 text-right")}>{fmtBRLCompact(r.pl)}</td>
                <td className={cx(tableTokens.cellNumberSecondary, "py-1.5 px-2 text-right")}>{fmtPct(r.pct_pl, 1)}</td>
                <td className={cx(tableTokens.cellNumber, "py-1.5 px-2 text-right")}>{fmtBRLCompact(r.pl_medio)}</td>
                <td className={cx(tableTokens.cellNumber, "py-1.5 px-2 text-right")}>{fmtBRLCompact(r.pl_mediano)}</td>
                <td className={cx(tableTokens.cellNumber, "py-1.5 pl-2 text-right")}>{fmtPct(r.liquidez_pct, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  )
}
