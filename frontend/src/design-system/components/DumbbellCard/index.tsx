// src/design-system/components/DumbbellCard/index.tsx
//
// Dumbbell chart pra Mix de produtos: prior_share vs current_share por
// categoria. Cada produto = uma linha horizontal com 2 dots (prior + current)
// conectados por uma reta. Util pra ler "X cresceu 3pp, Y caiu 2pp" no mesmo
// frame visual.
//
// Implementacao em ECharts via series scatter + custom render (linhas
// conectoras entre os dots).

"use client"

import * as React from "react"
import type { EChartsOption } from "echarts"

import {
  EChartsCard,
  type EChartsCardHeaderKpi,
} from "@/design-system/components/EChartsCard"
import type { Operacoes2DumbbellSeriesData } from "@/lib/api-client"

const COLOR_PRIOR = "#94A3B8" // slate-400 (anterior, mais discreto)
const COLOR_CURRENT_GAIN = "#10B981" // emerald-500 (current quando ganhou share)
const COLOR_CURRENT_LOSS = "#F43F5E" // rose-500 (current quando perdeu share)
const COLOR_LINE = "#CBD5E1" // slate-300 (conector)

const fmtPct1 = (v: number) => `${v.toFixed(1).replace(".", ",")}%`
const fmtPctSigned = (v: number) =>
  `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1).replace(".", ",")}pp`

export interface DumbbellCardProps {
  data: Operacoes2DumbbellSeriesData
  title: string
  caption?: string
  /**
   * KPI editorial no header (opt-in — Dumbbell nao tem KPI unico evidente,
   * caller decide qual mover destacar). Ex.: top mover do periodo.
   */
  headerKpi?: EChartsCardHeaderKpi
  height?: number
  footer?: React.ReactNode
  actions?: React.ReactNode
  className?: string
}

export function DumbbellCard({
  data,
  title,
  caption,
  headerKpi,
  height = 280,
  footer,
  actions,
  className,
}: DumbbellCardProps) {
  // Pontos ja vem ordenados por |delta_share_pp| desc do backend.
  // Inverte pra que o maior fique no topo do chart (yAxis 'category' eh top-down).
  const points = React.useMemo(() => [...data.points].reverse(), [data.points])

  const autoCaption = React.useMemo(() => {
    if (caption) return caption
    return `${data.prior_anchor_label} → ${data.current_anchor_label}`
  }, [data, caption])

  const option: EChartsOption = React.useMemo(() => {
    const categories = points.map((p) => p.member_label)
    // Linhas conectoras: cada linha vai de (prior_share, idx) a (current_share, idx)
    const linesData = points.map((p, idx) => [
      { value: [p.prior_share_pct, idx] },
      { value: [p.current_share_pct, idx] },
    ])
    const priorPoints = points.map((p, idx) => ({
      value: [p.prior_share_pct, idx],
      name: p.member_label,
      itemStyle: { color: COLOR_PRIOR },
    }))
    const currentPoints = points.map((p, idx) => ({
      value: [p.current_share_pct, idx],
      name: p.member_label,
      itemStyle: {
        color: p.delta_share_pp >= 0 ? COLOR_CURRENT_GAIN : COLOR_CURRENT_LOSS,
      },
    }))

    return {
      grid: { top: 24, right: 60, bottom: 28, left: 110 },
      xAxis: {
        type: "value",
        axisLabel: {
          formatter: (v: number) => `${v.toFixed(0)}%`,
          fontSize: 10,
        },
        splitLine: { lineStyle: { type: "dashed", opacity: 0.5 } },
      },
      yAxis: {
        type: "category",
        data: categories,
        axisLabel: { fontSize: 11, interval: 0 },
        axisTick: { show: false },
      },
      tooltip: {
        trigger: "item",
        formatter: (params: unknown) => {
          const p = params as { name?: string; data: { value: [number, number] } }
          const idx = Math.round(p.data?.value?.[1] ?? 0)
          const point = points[idx]
          if (!point) return ""
          return [
            `<b>${point.member_label}</b>`,
            `Anterior: ${fmtPct1(point.prior_share_pct)}`,
            `Atual: ${fmtPct1(point.current_share_pct)}`,
            `Δ ${fmtPctSigned(point.delta_share_pp)}`,
          ].join("<br/>")
        },
      },
      series: [
        // Linhas conectoras (uma "lines" por par)
        {
          name: "Conector",
          type: "lines",
          coordinateSystem: "cartesian2d",
          data: linesData.map((pair) => ({
            coords: pair.map((p) => p.value),
            lineStyle: { color: COLOR_LINE, width: 2 },
          })),
          silent: true,
          z: 1,
        },
        // Dots Prior
        {
          name: "Anterior",
          type: "scatter",
          coordinateSystem: "cartesian2d",
          symbolSize: 10,
          data: priorPoints,
          z: 2,
        },
        // Dots Current
        {
          name: "Atual",
          type: "scatter",
          coordinateSystem: "cartesian2d",
          symbolSize: 12,
          data: currentPoints,
          label: {
            show: true,
            position: "right",
            fontSize: 10,
            formatter: (params: { dataIndex: number }) => {
              const point = points[params.dataIndex]
              if (!point) return ""
              return fmtPctSigned(point.delta_share_pp)
            },
          },
          z: 3,
        },
      ],
    }
  }, [points])

  return (
    <EChartsCard
      option={option}
      title={title}
      caption={autoCaption}
      headerKpi={headerKpi}
      height={height}
      actions={actions}
      footer={footer}
      className={className}
    />
  )
}
