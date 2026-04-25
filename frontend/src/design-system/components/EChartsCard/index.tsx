// src/design-system/components/EChartsCard/index.tsx
// Wrapper around echarts-for-react.
// Adds: ResizeObserver reflow, caption slot, footer slot, error/retry,
//       notMerge + lazyUpdate defaults, useEChartsTheme() auto dark/light.

"use client"

import * as React from "react"
import ReactECharts from "echarts-for-react"
import type { EChartsOption } from "echarts"
import { RiErrorWarningLine, RiRefreshLine } from "@remixicon/react"
import { cx } from "@/lib/utils"
import { useEChartsTheme } from "@/design-system/tokens/echarts-theme"

export { useEChartsTheme }

function ChartSkeleton({ height }: { height: number }) {
  return (
    <div
      className="w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800"
      style={{ height }}
      aria-busy="true"
      aria-label="Carregando gráfico"
    />
  )
}

function ChartError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-8">
      <RiErrorWarningLine className="size-6 text-red-400" aria-hidden="true" />
      <p className="text-xs text-gray-500 dark:text-gray-400">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 px-2.5 py-1 text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-900 transition-colors"
        >
          <RiRefreshLine className="size-3.5" aria-hidden="true" />
          Tentar novamente
        </button>
      )}
    </div>
  )
}

export interface EChartsCardProps {
  option:        EChartsOption
  height?:       number
  loading?:      boolean
  error?:        string | null
  onRetry?:      () => void
  title?:        string
  caption?:      string
  actions?:      React.ReactNode
  footer?:       React.ReactNode
  className?:    string
  echartsProps?: Omit<React.ComponentProps<typeof ReactECharts>, "option" | "style">
}

export function EChartsCard({
  option,
  height  = 240,
  loading = false,
  error   = null,
  onRetry,
  title,
  caption,
  actions,
  footer,
  className,
  echartsProps,
}: EChartsCardProps) {
  const theme = useEChartsTheme()
  const chartRef = React.useRef<ReactECharts | null>(null)
  const containerRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const ro = new ResizeObserver(() => {
      chartRef.current?.getEchartsInstance()?.resize()
    })
    ro.observe(container)
    return () => ro.disconnect()
  }, [])

  const mergedOption: EChartsOption = React.useMemo(() => {
    const themeOption = theme as unknown as EChartsOption
    return {
      ...themeOption,
      backgroundColor: "transparent",
      ...option,
      animationDuration: option.animationDuration ?? theme.animationDuration,
      animationDurationUpdate: 0,
      tooltip: {
        ...(themeOption.tooltip as object),
        ...((option.tooltip as object) ?? {}),
      },
      axisPointer: {
        ...(themeOption.axisPointer as object),
        ...((option.axisPointer as object) ?? {}),
      },
    } as EChartsOption
  }, [option, theme])

  return (
    <div
      className={cx(
        "relative w-full rounded border shadow-xs",
        "bg-white dark:bg-[#090E1A]",
        "border-gray-200 dark:border-gray-900",
        className,
      )}
    >
      {(title || actions) && (
        <div className="flex items-start justify-between gap-3 border-b border-gray-100 dark:border-gray-900 px-4 py-3">
          <div className="min-w-0">
            {title && (
              <h3 className="truncate text-sm font-semibold text-gray-900 dark:text-gray-50">{title}</h3>
            )}
            {caption && (
              <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{caption}</p>
            )}
          </div>
          {actions && (
            <div className="flex shrink-0 items-center gap-2">{actions}</div>
          )}
        </div>
      )}

      <div ref={containerRef} className="px-4 py-3">
        {loading ? (
          <ChartSkeleton height={height} />
        ) : error ? (
          <div style={{ height }}>
            <ChartError message={error} onRetry={onRetry} />
          </div>
        ) : (
          <ReactECharts
            ref={chartRef}
            option={mergedOption}
            style={{ height, width: "100%" }}
            notMerge={false}
            lazyUpdate
            {...echartsProps}
          />
        )}
      </div>

      {footer && (
        <div className="border-t border-gray-100 dark:border-gray-900 px-4 py-2">
          {footer}
        </div>
      )}
    </div>
  )
}

export interface SparkChartProps {
  data:       number[]
  color?:     string
  height?:    number
  className?: string
}

export function SparkChart({ data, color = "#3B82F6", height = 40, className }: SparkChartProps) {
  const option: EChartsOption = {
    grid:  { top: 2, right: 2, bottom: 2, left: 2 },
    xAxis: { type: "category", show: false },
    yAxis: { type: "value", show: false },
    series: [{
      type:      "line",
      data,
      smooth:    true,
      symbol:    "none",
      lineStyle: { color, width: 1.5 },
      areaStyle: { color, opacity: 0.08 },
    }],
    animation: false,
  }
  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      className={className}
      notMerge
      lazyUpdate
    />
  )
}
