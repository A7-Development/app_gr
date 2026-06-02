// Aba Risco & Liquidez — matriz porte × condominio do indice de liquidez +
// serie temporal (ponderado vs fundo mediano).

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import type { EChartsOption } from "echarts"

import { EChartsCard } from "@/design-system/components/EChartsCard"
import { biPanorama } from "@/lib/api-client"
import type { PanoramaFilters, PanoramaLiquidezCell } from "@/lib/api-client"

import { competenciaShort } from "./format"
import { TabSkeleton, TabError } from "./_state"

// Ordem canonica das faixas de porte (eixo Y do heatmap).
const PORTE_ORDER = [
  "< R$ 50 mi",
  "R$ 50-200 mi",
  "R$ 200-500 mi",
  "R$ 500 mi-1 bi",
  "> R$ 1 bi",
]

export function RiscoLiquidezTab({ filters }: { filters: PanoramaFilters }) {
  const q = useQuery({
    queryKey: ["bi", "panorama", "risco-liquidez", filters],
    queryFn: () => biPanorama.riscoLiquidez(filters),
  })

  if (q.isLoading) return <TabSkeleton />
  if (q.isError || !q.data) return <TabError onRetry={() => q.refetch()} />

  const { matriz, serie } = q.data.data

  // Eixos do heatmap a partir das celulas presentes.
  const condoms = Array.from(new Set(matriz.map((c) => c.condom)))
  const portes = PORTE_ORDER.filter((p) => matriz.some((c) => c.porte === p))
  const cellByKey = new Map<string, PanoramaLiquidezCell>(
    matriz.map((c) => [`${c.condom}|${c.porte}`, c]),
  )
  const heatData: [number, number, number][] = []
  let maxVal = 1
  condoms.forEach((cond, xi) => {
    portes.forEach((porte, yi) => {
      const cell = cellByKey.get(`${cond}|${porte}`)
      const v = cell ? cell.indice_ponderado : 0
      maxVal = Math.max(maxVal, v)
      heatData.push([xi, yi, v])
    })
  })

  const heatOption: EChartsOption = {
    grid: { top: 12, right: 16, bottom: 28, left: 96 },
    xAxis: {
      type: "category",
      data: condoms,
      axisTick: { show: false },
      axisLabel: { fontSize: 11, color: "#6B7280" },
      splitArea: { show: true },
    },
    yAxis: {
      type: "category",
      data: portes,
      inverse: true,
      axisTick: { show: false },
      axisLabel: { fontSize: 11, color: "#6B7280" },
      splitArea: { show: true },
    },
    visualMap: {
      min: 0,
      max: Math.ceil(maxVal),
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      itemHeight: 80,
      textStyle: { fontSize: 10, color: "#6B7280" },
      inRange: { color: ["#EFF6FF", "#93C5FD", "#3B82F6", "#1E40AF"] },
      show: false,
    },
    series: [
      {
        type: "heatmap",
        data: heatData,
        label: {
          show: true,
          fontSize: 12,
          fontWeight: 600,
          formatter: (p: unknown) =>
            `${(p as { value: [number, number, number] }).value[2].toFixed(1).replace(".", ",")}%`,
          color: "#fff",
        },
        itemStyle: { borderColor: "#fff", borderWidth: 2 },
      },
    ],
    tooltip: {
      position: "top",
      formatter: (p: unknown) => {
        const d = (p as { value: [number, number, number] }).value
        const cell = cellByKey.get(`${condoms[d[0]]}|${portes[d[1]]}`)
        return `${portes[d[1]]} · ${condoms[d[0]]}<br/>Ponderado ${d[2].toFixed(1).replace(".", ",")}% · Mediano ${
          cell ? cell.mediana.toFixed(1).replace(".", ",") : "—"
        }%<br/>${cell ? cell.n_fidc : 0} fundos`
      },
    },
  }

  // Serie: ponderado (puxado pelos grandes) vs fundo mediano.
  const serieOption: EChartsOption = {
    grid: { top: 16, right: 16, bottom: 28, left: 44 },
    legend: { bottom: 0, textStyle: { fontSize: 11, color: "#6B7280" } },
    xAxis: {
      type: "category",
      data: serie.map((s) => competenciaShort(s.competencia)),
      axisTick: { show: false },
      axisLabel: { fontSize: 10, color: "#6B7280" },
    },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 11, color: "#6B7280", formatter: "{value}%" },
      splitLine: { lineStyle: { color: "rgba(107,114,128,0.15)" } },
    },
    series: [
      {
        name: "Ponderado (mercado)",
        type: "line",
        smooth: false,
        symbol: "none",
        data: serie.map((s) => s.indice_ponderado),
        lineStyle: { color: "#3B82F6", width: 2 },
      },
      {
        name: "Fundo mediano",
        type: "line",
        smooth: false,
        symbol: "none",
        data: serie.map((s) => s.mediana),
        lineStyle: { color: "#94A3B8", width: 2, type: "dashed" },
      },
    ],
    tooltip: { trigger: "axis", valueFormatter: (v) => `${Number(v).toFixed(2).replace(".", ",")}%` },
  }

  return (
    <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <EChartsCard
        title="LIQUIDEZ / PL · PORTE × CONDOMÍNIO"
        caption="Índice ponderado por célula. Extremos dos fechados (pequenos em ramp-up, grandes master-feeder) seguram mais caixa."
        option={heatOption}
        height={300}
      />
      <EChartsCard
        title="EVOLUÇÃO DO ÍNDICE DE LIQUIDEZ"
        caption="Ponderado (peso dos grandes) vs fundo mediano — o gap revela que os grandes seguram colchão e a cauda fica esticada."
        option={serieOption}
        height={300}
      />
    </section>
  )
}
