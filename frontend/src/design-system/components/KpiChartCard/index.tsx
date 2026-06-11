// src/design-system/components/KpiChartCard/index.tsx
//
// Card de gráfico canônico da esteira (handoff Conceito D + ui_kits/app-gr/
// charts.jsx). Anatomia validada contra o chart real de variação diária
// da cota:
//
//   L1  eyebrow uppercase 11px/600 tracking 0.06em
//   L2  KPI 22px/700 tracking -0.025em tabular + delta 13px/600 + sufixo 12px
//   L3  linha de contexto 13px muted
//   Gráfico: barras navy #1B2B4B (55% do slot, radius 2), rótulo de valor
//   sobre cada barra (10px/500 #4B5563), barra SELECIONADA em #0EA5E9
//   (rótulo do eixo X em #0284C7/600), eixo Y 10px #9CA3AF, gridlines
//   gray-100 (linha do zero gray-300).
//
// O protótipo usa SVG estático; aqui é ECharts com a MESMA anatomia
// (README do handoff). Hex inline é permitido em EChartsOption (§4).

"use client"

import * as React from "react"
import ReactECharts from "echarts-for-react"
import type { EChartsOption } from "echarts"

import { Card } from "@/components/tremor/Card"
import { tokens } from "@/design-system/tokens"
import { cx } from "@/lib/utils"

export type KpiChartDatum = {
  label: string
  value: number
  /** Rótulo formatado sobre a barra (ex.: "2,41"). Omitido = sem rótulo. */
  valueLabel?: string
  /** Barra selecionada (azul claro #0EA5E9). No dossiê compilado, nunca. */
  selected?: boolean
}

export type KpiChartCardProps = {
  eyebrow: string
  value: string
  delta?: string
  deltaSuffix?: string
  /** Tom do delta (default pos = verde). */
  deltaTone?: "pos" | "neg" | "neu"
  context?: string
  data: KpiChartDatum[]
  yTicks?: Array<{ v: number; label: string }>
  yMax?: number
  height?: number
  /** Clicar numa barra (índice) — na estação, foca a linha da tabela. */
  onBarClick?: (index: number) => void
  className?: string
}

function compactAxisLabel(v: number): string {
  if (v === 0) return "0"
  const fmt = (n: number) =>
    n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })
  if (Math.abs(v) >= 1_000_000_000) return `${fmt(v / 1_000_000_000)} bi`
  if (Math.abs(v) >= 1_000_000) return `${fmt(v / 1_000_000)} mi`
  if (Math.abs(v) >= 1_000) return `${fmt(v / 1_000)} mil`
  return fmt(v)
}

const BAR_NAVY = "#1B2B4B"
const BAR_SELECTED = "#0EA5E9"
const AXIS_LABEL = "#9CA3AF"
const AXIS_LABEL_SELECTED = "#0284C7"
const VALUE_LABEL = "#4B5563"
const GRID_LINE = "#F3F4F6"
const ZERO_LINE = "#D1D5DB"

export function KpiChartCard({
  eyebrow,
  value,
  delta,
  deltaSuffix,
  deltaTone = "pos",
  context,
  data,
  yTicks = [],
  yMax,
  height = 280,
  onBarClick,
  className,
}: KpiChartCardProps) {
  const max = yMax ?? (Math.max(...data.map((d) => d.value), 0) * 1.1 || 1)

  const option = React.useMemo<EChartsOption>(() => {
    const selectedIdx = data.findIndex((d) => d.selected)
    return {
      animationDuration: 150,
      grid: { left: 48, right: 10, top: 18, bottom: 20, containLabel: false },
      xAxis: {
        type: "category",
        data: data.map((d) => d.label),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          fontSize: 10,
          fontFamily: "Inter, sans-serif",
          color: (_value?: string | number, index?: number) =>
            index === selectedIdx ? AXIS_LABEL_SELECTED : AXIS_LABEL,
          fontWeight: 400,
          margin: 8,
        },
      },
      yAxis: {
        type: "value",
        max,
        interval: undefined,
        axisLabel: yTicks.length
          ? {
              fontSize: 10,
              fontFamily: "Inter, sans-serif",
              color: AXIS_LABEL,
              formatter: (v: number) => {
                const tick = yTicks.find((t) => Math.abs(t.v - v) < 1e-9)
                return tick ? tick.label : ""
              },
            }
          : {
              fontSize: 10,
              fontFamily: "Inter, sans-serif",
              color: AXIS_LABEL,
              formatter: (v: number) => compactAxisLabel(v),
            },
        splitLine: {
          lineStyle: { color: GRID_LINE, width: 1 },
        },
        axisLine: { show: false },
        axisTick: { show: false },
        ...(yTicks.length
          ? {
              min: Math.min(...yTicks.map((t) => t.v), 0),
              splitNumber: yTicks.length - 1,
              interval:
                yTicks.length > 1
                  ? (yTicks[1].v - yTicks[0].v)
                  : undefined,
            }
          : {}),
      },
      series: [
        {
          type: "bar",
          barWidth: "55%",
          data: data.map((d) => ({
            value: d.value,
            itemStyle: {
              color: d.selected ? BAR_SELECTED : BAR_NAVY,
              borderRadius: [2, 2, 0, 0],
            },
            label: d.valueLabel
              ? {
                  show: true,
                  position: "top" as const,
                  distance: 5,
                  fontSize: 10,
                  fontWeight: 500,
                  fontFamily: "Inter, sans-serif",
                  color: VALUE_LABEL,
                  formatter: () => d.valueLabel ?? "",
                }
              : { show: false },
          })),
          markLine:
            yTicks.some((t) => t.v === 0)
              ? {
                  silent: true,
                  symbol: "none",
                  label: { show: false },
                  data: [{ yAxis: 0 }],
                  lineStyle: { color: ZERO_LINE, width: 1, type: "solid" as const },
                }
              : undefined,
          cursor: onBarClick ? "pointer" : "default",
        },
      ],
      tooltip: { show: false },
    }
  }, [data, max, yTicks, onBarClick])

  const deltaColor = tokens.colors.delta[deltaTone].light

  const onEvents = React.useMemo(
    () =>
      onBarClick
        ? {
            click: (params: { dataIndex?: number }) => {
              if (typeof params.dataIndex === "number") onBarClick(params.dataIndex)
            },
          }
        : undefined,
    [onBarClick],
  )

  return (
    <Card className={cx("p-4", className)}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
        {eyebrow}
      </p>
      <p className="mt-1 flex items-baseline gap-2">
        <span className="text-[22px] font-bold tracking-[-0.025em] text-gray-900 tabular-nums dark:text-gray-50">
          {value}
        </span>
        {delta && (
          <span
            className="text-[13px] font-semibold tabular-nums"
            style={{ color: deltaColor }}
          >
            {delta}
          </span>
        )}
        {deltaSuffix && (
          <span className="text-xs text-gray-500 dark:text-gray-400">{deltaSuffix}</span>
        )}
      </p>
      {context && (
        <p className="mt-1 text-[13px] text-gray-500 dark:text-gray-400">{context}</p>
      )}
      <div className="mt-3.5" style={{ height }}>
        <ReactECharts
          option={option}
          style={{ height: "100%", width: "100%" }}
          notMerge
          onEvents={onEvents}
        />
      </div>
    </Card>
  )
}
