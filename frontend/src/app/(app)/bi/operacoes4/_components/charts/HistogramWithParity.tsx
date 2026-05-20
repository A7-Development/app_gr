// src/app/(app)/bi/operacoes4/_components/charts/HistogramWithParity.tsx
//
// L6 — histograma de distribuicao (taxas ou prazos) com:
//   - barras solidas: MTD por bucket (cor canonica chart[1] = sky-500)
//   - linha tracejada: paridade DU do mes anterior (slate-400)
//   - bucket de cauda colorido AMBAR quando `tailFlag: true` (sinaliza
//     concentracao acima/abaixo de limite definido pelo caller).
//
// Reuso entre Taxa e Prazo via `xAxisLabel` + `valueSuffix` configuraveis.
// O eixo Y representa volume R$ M (BRL milhoes) no exemplo do handoff.

"use client"

import * as React from "react"
import type { EChartsOption } from "echarts"

import { EChartsCard } from "@/design-system/components/EChartsCard"
import { tokens } from "@/design-system/tokens"

export interface HistogramBucket {
  label: string
  /** Valor MTD (R$ milhoes ou unidade do caller). */
  atual: number
  /** Valor da paridade DU mes anterior. */
  parity: number
  /** True quando o bucket esta em zona de atencao (cauda). */
  tailFlag?: boolean
}

export interface HistogramWithParityProps {
  data: HistogramBucket[]
  /** Label do eixo X (ex.: "Taxa (% a.m.)" ou "Prazo (dias)"). */
  xAxisLabel?: string
  /** Sufixo do tooltip nos valores (ex.: " M" ou ""). Default: "". */
  valueSuffix?: string
  height?: number
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  embedded?: boolean
}

const BAR_MTD = tokens.colors.chart[1] // sky-500
const LINE_PARITY = "#94A3B8" // slate-400
const TAIL_AMBER = "#D97706"

function fmtNum(v: number, suffix: string): string {
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}${suffix}`
}

export function HistogramWithParity({
  data,
  xAxisLabel,
  valueSuffix = "",
  height = 220,
  loading,
  error,
  onRetry,
  embedded = true,
}: HistogramWithParityProps) {
  const option: EChartsOption = React.useMemo(() => {
    const labels = data.map((b) => b.label)
    const atual = data.map((b) => ({
      value: b.atual,
      itemStyle: { color: b.tailFlag ? TAIL_AMBER : BAR_MTD },
    }))
    const parity = data.map((b) => b.parity)

    return {
      grid: { top: 18, right: 16, bottom: xAxisLabel ? 40 : 28, left: 36, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params: unknown) => {
          const arr = params as Array<{
            axisValueLabel: string
            seriesName: string
            value: number
            marker: string
          }>
          if (!arr || arr.length === 0) return ""
          const head = arr[0].axisValueLabel
          const lines = arr
            .map(
              (p) =>
                `${p.marker} ${p.seriesName}: <b>${fmtNum(p.value, valueSuffix)}</b>`,
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
        name: xAxisLabel,
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { fontSize: 10, color: "#6B7280" },
        axisLabel: { fontSize: 10, color: "#6B7280", interval: 0 },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#E5E7EB" } },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          fontSize: 10,
          color: "#6B7280",
          formatter: (v: number) => fmtNum(v, valueSuffix),
        },
        splitLine: { lineStyle: { color: "#F3F4F6", type: "dashed" } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          name: "MTD",
          type: "bar",
          data: atual,
          barMaxWidth: 32,
          z: 2,
        },
        {
          name: "Paridade DU",
          type: "line",
          data: parity,
          smooth: false,
          symbol: "circle",
          symbolSize: 5,
          lineStyle: { color: LINE_PARITY, width: 1.5, type: "dashed" },
          itemStyle: { color: LINE_PARITY },
          z: 3,
        },
      ],
    } satisfies EChartsOption
  }, [data, xAxisLabel, valueSuffix])

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
