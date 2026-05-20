// src/app/(app)/bi/operacoes4/_components/charts/YieldChart.tsx
//
// L3 direita — yield efetivo (receita/VOP) por DU. Linha solida MTD, linha
// tracejada paridade DU do mes anterior, ponto destacado no DU corrente
// (today). Usa EChartsCard (auto theme + ResizeObserver).
//
// Cores (hex literals permitidos dentro de EChartsOption — exception §4.2):
//   - Linha MTD:        #3B82F6 (blue-500) — alinha com "atencao" da §4
//   - Linha paridade:   #94A3B8 (slate-400) dashed
//   - Ponto today:      #3B82F6 com halo branco
//
// Recebe so dados; o card envolvente (com header KPI + actions) e
// responsabilidade do caller (PR3).

"use client"

import * as React from "react"
import type { EChartsOption } from "echarts"

import { EChartsCard } from "@/design-system/components/EChartsCard"

export interface YieldPonto {
  du: number
  yieldPct: number
  yieldParityPct: number | null
  today: boolean
}

export interface YieldChartProps {
  data: YieldPonto[]
  height?: number
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  /** Quando true, esconde o wrapper de Card (so o canvas). */
  embedded?: boolean
}

const LINE_MTD = "#3B82F6"
const LINE_PARITY = "#94A3B8"

function fmtPct(v: number): string {
  return `${v.toFixed(2).replace(".", ",")}%`
}

export function YieldChart({
  data,
  height = 200,
  loading,
  error,
  onRetry,
  embedded = true,
}: YieldChartProps) {
  const option: EChartsOption = React.useMemo(() => {
    const labels = data.map((d) => `DU ${d.du}`)
    const serieMtd = data.map((d) => ({
      value: d.yieldPct,
      symbol: d.today ? "circle" : "none",
      symbolSize: d.today ? 8 : 0,
      itemStyle: d.today
        ? {
            color: LINE_MTD,
            borderColor: "#FFFFFF",
            borderWidth: 2,
            shadowColor: LINE_MTD,
            shadowBlur: 4,
          }
        : { color: LINE_MTD },
    }))
    const serieParity = data.map((d) =>
      d.yieldParityPct === null ? null : d.yieldParityPct,
    )

    return {
      grid: { top: 16, right: 16, bottom: 28, left: 40, containLabel: true },
      tooltip: {
        trigger: "axis",
        formatter: (params: unknown) => {
          const arr = params as Array<{
            axisValueLabel: string
            seriesName: string
            value: number | null
            marker: string
          }>
          if (!arr || arr.length === 0) return ""
          const head = arr[0].axisValueLabel
          const lines = arr
            .filter((p) => p.value !== null && p.value !== undefined)
            .map(
              (p) =>
                `${p.marker} ${p.seriesName}: <b>${fmtPct(p.value as number)}</b>`,
            )
            .join("<br/>")
          return `<div style="font-size:11px"><b>${head}</b><br/>${lines}</div>`
        },
      },
      legend: {
        show: true,
        right: 0,
        top: 0,
        textStyle: { fontSize: 10, color: "#6B7280" },
        icon: "roundRect",
        itemWidth: 8,
        itemHeight: 8,
      },
      xAxis: {
        type: "category",
        data: labels,
        boundaryGap: false,
        axisLabel: { fontSize: 10, color: "#6B7280" },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#E5E7EB" } },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          fontSize: 10,
          color: "#6B7280",
          formatter: (v: number) => fmtPct(v),
        },
        splitLine: { lineStyle: { color: "#F3F4F6", type: "dashed" } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          name: "MTD",
          type: "line",
          data: serieMtd,
          smooth: false,
          symbol: "none",
          lineStyle: { color: LINE_MTD, width: 2 },
          z: 3,
        },
        {
          name: "Paridade DU",
          type: "line",
          data: serieParity,
          smooth: false,
          symbol: "none",
          lineStyle: { color: LINE_PARITY, width: 1.5, type: "dashed" },
          z: 2,
        },
      ],
    } satisfies EChartsOption
  }, [data])

  return (
    <EChartsCard
      option={option}
      height={height}
      loading={loading}
      error={error}
      onRetry={onRetry}
      embedded={embedded}
    />
  )
}
