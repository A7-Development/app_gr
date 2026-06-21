"use client"

//
// HistoricoCard — evolutivo diario do TOP 1, TOP 5 e TOP 10 sobre o PL (3
// linhas). Header com trio de KPIs color-coded (= legenda + valor atual de cada
// linha; substitui a legenda do chart). Estilo /bi/operacoes4. Hex inline
// permitido em EChartsOption + cor dinamica de serie (§4).
//

import * as React from "react"
import type { EChartsOption } from "echarts"

import { Card } from "@/components/tremor/Card"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import { cx } from "@/lib/utils"
import type { ConcentracaoHistoricoPonto } from "@/lib/api-client"

const fmtPct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})
function pct1(v: number | null | undefined): string {
  return v == null ? "—" : `${fmtPct.format(v)}%`
}

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
function monthLabel(iso: string): string {
  const d = new Date(iso)
  return `${MESES[d.getUTCMonth()]}/${String(d.getUTCFullYear()).slice(2)}`
}

// Gradiente de concentracao: TOP 1 escuro -> TOP 10 claro (slate/blue).
const COR_TOP1 = "#1E293B"
const COR_TOP5 = "#2563EB"
const COR_TOP10 = "#93C5FD"

export function HistoricoCard({
  titulo,
  pontos,
  loading,
}: {
  titulo: string
  pontos: ConcentracaoHistoricoPonto[]
  loading: boolean
}) {
  // Valores "hoje" = ultimo ponto do historico (casa com o fim das linhas).
  const last = pontos.length > 0 ? pontos[pontos.length - 1] : undefined
  const kpis = [
    { label: "Top 1", value: pct1(last?.maior_pct), color: COR_TOP1 },
    { label: "Top 5", value: pct1(last?.top5_pct), color: COR_TOP5 },
    { label: "Top 10", value: pct1(last?.top10_pct), color: COR_TOP10 },
  ]

  const option = React.useMemo<EChartsOption>(() => {
    const datas = pontos.map((p) => p.data)
    const top1 = pontos.map((p) => Number(p.maior_pct.toFixed(2)))
    const top5 = pontos.map((p) => Number(p.top5_pct.toFixed(2)))
    const top10 = pontos.map((p) => Number(p.top10_pct.toFixed(2)))

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
      // Rotulo na PONTA da linha (legenda na propria serie).
      endLabel: {
        show: true,
        formatter: () => name,
        color,
        fontSize: 11,
        fontWeight: 600,
        fontFamily: "Inter, sans-serif",
        offset: [4, 0],
      },
    })

    return {
      // Legenda OFF (show:false p/ sobrescrever o default do tema) — o trio de
      // KPIs no header ja rotula as 3 linhas.
      legend: { show: false },
      // right maior p/ caber o endLabel ("Top 10") na ponta das linhas.
      grid: { left: 38, right: 56, top: 12, bottom: 22 },
      tooltip: { trigger: "axis", valueFormatter: (v) => `${Number(v).toFixed(1)}%` },
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
        line("Top 1", top1, COR_TOP1),
        line("Top 5", top5, COR_TOP5),
        line("Top 10", top10, COR_TOP10),
      ],
    }
  }, [pontos])

  return (
    <Card className="p-0">
      {/* Header: eyebrow + trio de KPIs color-coded (legenda + valor atual). */}
      <div className="px-4 pt-4">
        <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
          {titulo}
        </p>
        <div className="mt-2 flex items-stretch">
          {kpis.map((k, idx) => (
            <div
              key={k.label}
              className={cx(
                "flex flex-col justify-start",
                idx === 0
                  ? "pr-[18px]"
                  : "border-l border-gray-200 px-[18px] dark:border-gray-800",
              )}
            >
              <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-400 dark:text-gray-500">
                <span
                  className="size-[7px] shrink-0 rounded-[2px]"
                  style={{ backgroundColor: k.color }}
                  aria-hidden
                />
                {k.label}
              </p>
              <span className="mt-[3px] text-[20px] font-bold leading-none tabular-nums text-gray-900 dark:text-gray-50">
                {k.value}
              </span>
            </div>
          ))}
        </div>
      </div>

      <EChartsCard embedded option={option} height={372} loading={loading} />
    </Card>
  )
}
