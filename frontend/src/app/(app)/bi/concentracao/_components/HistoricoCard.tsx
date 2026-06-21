"use client"

//
// HistoricoCard — serie diaria de concentracao: evolutivo do TOP 1, TOP 5 e
// TOP 10 sobre o PL (3 linhas). Estilo /bi/operacoes4. Hex inline permitido em
// EChartsOption (§4 — Tailwind nao alcanca o canvas). Altura pareada com a
// tabela de concentracao ao lado (simetria).
//

import * as React from "react"
import type { EChartsOption } from "echarts"

import { EChartsCard } from "@/design-system/components/EChartsCard"
import type { ConcentracaoHistoricoPonto } from "@/lib/api-client"

const fmtPct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

function monthLabel(iso: string): string {
  const d = new Date(iso)
  return `${MESES[d.getUTCMonth()]}/${String(d.getUTCFullYear()).slice(2)}`
}

// Gradiente de concentracao: TOP 1 mais escuro -> TOP 10 mais claro
// (familia slate/blue da paleta de dados).
const COR_TOP1 = "#1E293B"
const COR_TOP5 = "#2563EB"
const COR_TOP10 = "#93C5FD"

export function HistoricoCard({
  titulo,
  pontos,
  kpiTop10,
  kpiMaior,
  loading,
}: {
  titulo: string
  pontos: ConcentracaoHistoricoPonto[]
  kpiTop10: number
  kpiMaior: number
  loading: boolean
}) {
  const option = React.useMemo<EChartsOption>(() => {
    const datas = pontos.map((p) => p.data)
    const top1 = pontos.map((p) => Number(p.maior_pct.toFixed(2)))
    const top5 = pontos.map((p) => Number(p.top5_pct.toFixed(2)))
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
        { offset: 0, color: `${hex}33` },
        { offset: 1, color: `${hex}00` },
      ],
    })

    const line = (name: string, data: number[], color: string) => ({
      name,
      type: "line" as const,
      data,
      showSymbol: false,
      smooth: false,
      lineStyle: { width: 1.5, color },
      itemStyle: { color },
      areaStyle: { color: gradient(color) },
    })

    return {
      legend: {
        data: ["TOP 1", "TOP 5", "TOP 10"],
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
        line("TOP 1", top1, COR_TOP1),
        line("TOP 5", top5, COR_TOP5),
        line("TOP 10", top10, COR_TOP10),
      ],
    }
  }, [pontos])

  return (
    <EChartsCard
      title={titulo}
      headerKpi={{
        value: `${fmtPct.format(kpiTop10)}%`,
        deltaSub: `Top 10 hoje · Top 1 ${fmtPct.format(kpiMaior)}%`,
      }}
      option={option}
      height={372}
      loading={loading}
    />
  )
}
