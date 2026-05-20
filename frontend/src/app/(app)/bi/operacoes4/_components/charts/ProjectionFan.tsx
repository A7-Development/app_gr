// src/app/(app)/bi/operacoes4/_components/charts/ProjectionFan.tsx
//
// L2 direita — VOP acumulado MTD + 3 cenarios de fechamento (pessimista,
// realista, otimista). Linha solida MTD ate o DU corrente; 3 linhas
// pontilhadas curtas em direcao ao DU final, cada uma terminando no valor
// projetado do cenario. Marker HOJE no DU corrente.
//
// Quando os dados ainda nao tem cenario (degraded mode sem `wh_dim_dia_util`
// ou MTD vazio), o caller passa `scenarios` vazio — chart mostra so a
// linha realizada.

"use client"

import * as React from "react"
import type { EChartsOption } from "echarts"

import { EChartsCard } from "@/design-system/components/EChartsCard"

export interface ProjectionScenario {
  label: string
  finalValor: number
}

export interface ProjectionFanProps {
  /** Valor acumulado por DU do MTD (apenas DUs ja decorridos). */
  realizado: number[]
  /** Total de DUs do mes (eixo X cobre 1..duTotaisMes). */
  duLabels: string[]
  /** DU corrente — 1-indexed. realizado.length deve ser <= duCorrente. */
  duCorrente: number
  /** 3 cenarios (P25 / realista / P75). Sem cenarios = degraded. */
  scenarios?: ProjectionScenario[]
  /** Unidade da serie no tooltip (ex.: "R$ M"). */
  valueUnit?: string
  height?: number
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  embedded?: boolean
}

const LINE_REALIZADO = "#3B82F6" // blue-500
const LINE_OPT = "#10B981" // emerald-500
const LINE_REAL = "#94A3B8" // slate-400
const LINE_PESS = "#F43F5E" // rose-500

function fmtNum(v: number, suffix: string): string {
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}${suffix}`
}

export function ProjectionFan({
  realizado,
  duLabels,
  duCorrente,
  scenarios = [],
  valueUnit = "",
  height = 220,
  loading,
  error,
  onRetry,
  embedded = true,
}: ProjectionFanProps) {
  const option: EChartsOption = React.useMemo(() => {
    const ultimoRealizado = realizado[realizado.length - 1] ?? 0

    // Padroniza realizado pra ter exatamente `duCorrente` pontos. Demais
    // posicoes do eixo X (futuro) ficam null no array da serie principal.
    const realizadoEixo: (number | null)[] = duLabels.map((_, i) =>
      i < realizado.length ? realizado[i] : null,
    )

    // Cada cenario: linha tracejada do ultimo realizado ate o valor final
    // no ultimo DU. Demais posicoes = null pra ECharts unir so essas 2.
    const cenarioSeries =
      scenarios.length === 0
        ? []
        : scenarios.map((sc, idx) => {
            const color =
              idx === 0 ? LINE_PESS : idx === 1 ? LINE_REAL : LINE_OPT
            const lastIdx = duLabels.length - 1
            const startIdx = duCorrente - 1
            const data: (number | null)[] = duLabels.map((_, i) => {
              if (i === startIdx) return ultimoRealizado
              if (i === lastIdx) return sc.finalValor
              return null
            })
            return {
              name: sc.label,
              type: "line" as const,
              data,
              connectNulls: true,
              smooth: false,
              symbol: "circle",
              symbolSize: (_v: number, params: { dataIndex?: number }) =>
                params.dataIndex === lastIdx ? 6 : 0,
              lineStyle: { color, width: 1.5, type: "dashed" as const },
              itemStyle: { color },
              label: {
                show: true,
                position: "right" as const,
                fontSize: 10,
                color,
                formatter: (p: { dataIndex: number; value: unknown }) => {
                  const v = p.value
                  if (p.dataIndex === lastIdx && typeof v === "number") {
                    return fmtNum(v, valueUnit)
                  }
                  return ""
                },
              },
              z: 2,
            }
          })

    return {
      grid: { top: 18, right: 56, bottom: 28, left: 40, containLabel: true },
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
                `${p.marker} ${p.seriesName}: <b>${fmtNum(p.value as number, valueUnit)}</b>`,
            )
            .join("<br/>")
          if (!lines) return ""
          return `<div style="font-size:11px"><b>${head}</b><br/>${lines}</div>`
        },
      },
      legend: {
        show: scenarios.length > 0,
        right: 0,
        top: 0,
        textStyle: { fontSize: 10, color: "#6B7280" },
        icon: "roundRect",
        itemWidth: 8,
        itemHeight: 8,
      },
      xAxis: {
        type: "category",
        data: duLabels,
        boundaryGap: false,
        axisLabel: {
          fontSize: 10,
          color: "#6B7280",
          interval: Math.max(1, Math.floor(duLabels.length / 6)),
        },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#E5E7EB" } },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          fontSize: 10,
          color: "#6B7280",
          formatter: (v: number) => fmtNum(v, valueUnit),
        },
        splitLine: { lineStyle: { color: "#F3F4F6", type: "dashed" } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          name: "Realizado MTD",
          type: "line",
          data: realizadoEixo,
          smooth: false,
          symbol: "circle",
          symbolSize: (_v: number, params: { dataIndex?: number }) =>
            params.dataIndex === duCorrente - 1 ? 7 : 0,
          lineStyle: { color: LINE_REALIZADO, width: 2 },
          itemStyle: {
            color: LINE_REALIZADO,
            borderColor: "#FFFFFF",
            borderWidth: 2,
          },
          z: 3,
        },
        ...cenarioSeries,
      ],
    } satisfies EChartsOption
  }, [realizado, duLabels, duCorrente, scenarios, valueUnit])

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
