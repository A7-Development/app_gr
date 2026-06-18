"use client"

//
// HistoricoCard — serie diaria de concentracao (% do maior e % dos 10 maiores
// sobre o PL). Linha/area no estilo /bi/operacoes4. Hex inline permitido em
// EChartsOption (§4 — Tailwind nao alcanca o canvas).
//

import * as React from "react"
import type { EChartsOption } from "echarts"

import { EChartsCard } from "@/design-system/components/EChartsCard"
import type { ConcentracaoHistoricoPonto } from "@/lib/api-client"

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

function monthLabel(iso: string): string {
  const d = new Date(iso)
  return `${MESES[d.getUTCMonth()]}/${String(d.getUTCFullYear()).slice(2)}`
}

// Cor escura (maior) + azul claro (10 maiores) — familia slate/sky da paleta
// de dados; reproduz o contraste do handoff.
const COR_MAIOR = "#1E293B"
const COR_TOP10 = "#60A5FA"

export function HistoricoCard({
  titulo,
  labelMaior,
  pontos,
  loading,
}: {
  titulo: string
  labelMaior: string
  pontos: ConcentracaoHistoricoPonto[]
  loading: boolean
}) {
  const option = React.useMemo<EChartsOption>(() => {
    const datas = pontos.map((p) => p.data)
    const maior = pontos.map((p) => Number(p.maior_pct.toFixed(2)))
    const top10 = pontos.map((p) => Number(p.top10_pct.toFixed(2)))

    // Mostra label so na 1a data de cada mes (serie diaria -> ticks mensais).
    const mesFirst = new Set<number>()
    let prevKey = ""
    datas.forEach((iso, i) => {
      const d = new Date(iso)
      const key = `${d.getUTCFullYear()}-${d.getUTCMonth()}`
      if (key !== prevKey) {
        mesFirst.add(i)
        prevKey = key
      }
    })

    const gradient = (hex: string) => ({
      type: "linear" as const,
      x: 0,
      y: 0,
      x2: 0,
      y2: 1,
      colorStops: [
        { offset: 0, color: `${hex}40` },
        { offset: 1, color: `${hex}00` },
      ],
    })

    return {
      legend: {
        data: [labelMaior, "10 maiores"],
        top: 0,
        left: 0,
        icon: "roundRect",
        itemWidth: 10,
        itemHeight: 10,
        itemGap: 14,
        textStyle: { fontSize: 11, color: "#6B7280" },
      },
      grid: { left: 38, right: 12, top: 30, bottom: 22 },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v) => `${Number(v).toFixed(1)}%`,
      },
      xAxis: {
        type: "category",
        data: datas,
        boundaryGap: false,
        axisTick: { show: false },
        axisLabel: {
          fontSize: 10,
          color: "#9CA3AF",
          interval: (i: number) => mesFirst.has(i),
          formatter: (v: string) => monthLabel(v),
        },
      },
      yAxis: {
        type: "value",
        min: 0,
        axisLabel: { fontSize: 10, color: "#9CA3AF", formatter: (v: number) => `${v}%` },
        splitLine: { lineStyle: { color: "#F3F4F6" } },
      },
      series: [
        {
          name: labelMaior,
          type: "line",
          data: maior,
          showSymbol: false,
          smooth: false,
          lineStyle: { width: 1.5, color: COR_MAIOR },
          itemStyle: { color: COR_MAIOR },
          areaStyle: { color: gradient(COR_MAIOR) },
        },
        {
          name: "10 maiores",
          type: "line",
          data: top10,
          showSymbol: false,
          smooth: false,
          lineStyle: { width: 1.5, color: COR_TOP10 },
          itemStyle: { color: COR_TOP10 },
          areaStyle: { color: gradient(COR_TOP10) },
        },
      ],
    }
  }, [pontos, labelMaior])

  return (
    <EChartsCard title={titulo} option={option} height={260} loading={loading} />
  )
}
