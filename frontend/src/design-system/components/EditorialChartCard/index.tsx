// src/design-system/components/EditorialChartCard/index.tsx
//
// Wrapper editorial para chart hero estilo Goldman/FT/Economist.
//
// Diferenca chave vs `EChartsCard` (em `../EChartsCard`):
//   - EChartsCard: chart "interno" denso, vive em Card, titulo pequeno,
//     usado em grids alongado de widgets dashboard.
//   - EditorialChartCard: chart manchete, sem Card por default
//     ("respira" na pagina), titulo grande tipografia editorial,
//     subtitle descritivo, source row ancorado embaixo + watermark Strata.
//
// Anatomia (default, sem borda):
//
//   <eyebrow>           ← opcional, "BI · Operacao"
//   <title>             ← text-[22px] semibold tracking-tight
//   <subtitle>          ← text-[13px] gray-500, 1-2 linhas
//
//   ┌──────────────────────────────────────────────┐
//   │           <ReactECharts ... />               │
//   └──────────────────────────────────────────────┘
//
//   ────────────────────────────────────────────────  ← divider
//   Source: <source>            <StrataIcon size=20/>
//   <updatedAt>
//
// `bordered={true}` envolve em `<Card>` Tremor — use quando o chart precisar
// conviver visualmente com `EChartsCard` em grid, e o desencaixe naked
// vs bordered for um problema. Default e SEM borda (o look editorial).
//
// Reusa: `useEChartsTheme()` (mesma policy de merge do EChartsCard) +
// padrao de ResizeObserver + SkeletonChart + ErrorChart.

"use client"

import * as React from "react"
import ReactECharts from "echarts-for-react"
import type { EChartsOption } from "echarts"
import { RiErrorWarningLine, RiRefreshLine } from "@remixicon/react"

import { Card } from "@/components/tremor/Card"
import { useEChartsTheme } from "@/design-system/tokens/echarts-theme"
import { StrataIcon } from "@/design-system/components/StrataIcon"
import { cx } from "@/lib/utils"

export type EditorialChartCardProps = {
  title: string
  subtitle?: string
  /** Eyebrow uppercase acima do titulo. Ex.: "BI · Operacao". */
  eyebrow?: string
  /** Texto do source no rodape (ex.: "Bitfin · sincronizado em 04/05 14:32"). */
  source?: string
  /** Sub-source / cadencia. Renderiza em segunda linha do rodape. */
  updatedAt?: string
  height?: number
  option: EChartsOption
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  /** Mostra a marca Strata no canto inferior direito. Default: true. */
  showWatermark?: boolean
  /**
   * Envolve em Card (border + shadow + bg). Default: false (look editorial).
   * Use quando o chart precisar conviver com EChartsCards em grid.
   */
  bordered?: boolean
  className?: string
}

export function EditorialChartCard({
  title,
  subtitle,
  eyebrow,
  source,
  updatedAt,
  height = 360,
  option,
  loading = false,
  error = null,
  onRetry,
  showWatermark = true,
  bordered = false,
  className,
}: EditorialChartCardProps) {
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

  const inner = (
    <>
      {eyebrow && (
        <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400 mb-2">
          {eyebrow}
        </p>
      )}
      <h2 className="text-[22px] font-semibold tracking-tight leading-tight text-gray-900 dark:text-gray-50">
        {title}
      </h2>
      {subtitle && (
        <p className="mt-1.5 max-w-[55ch] text-[13px] leading-relaxed text-gray-500 dark:text-gray-400">
          {subtitle}
        </p>
      )}

      <div ref={containerRef} className="mt-5 mb-4">
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
          />
        )}
      </div>

      {(source || updatedAt || showWatermark) && (
        <div className="flex items-end justify-between gap-4 border-t border-gray-200 dark:border-gray-800 pt-3">
          <div className="flex flex-col gap-0.5 text-[11px] text-gray-500 dark:text-gray-400">
            {source && (
              <p>
                <span className="font-medium text-gray-600 dark:text-gray-300">
                  Fonte:
                </span>{" "}
                {source}
              </p>
            )}
            {updatedAt && <p>{updatedAt}</p>}
          </div>
          {showWatermark && (
            <StrataIcon
              height={20}
              tone="onLight"
              className="opacity-60 dark:hidden"
            />
          )}
          {showWatermark && (
            <StrataIcon
              height={20}
              tone="onDark"
              className="hidden opacity-60 dark:block"
            />
          )}
        </div>
      )}
    </>
  )

  if (bordered) {
    return <Card className={cx("relative p-6", className)}>{inner}</Card>
  }

  return (
    <div className={cx("relative w-full px-1 py-2", className)}>{inner}</div>
  )
}

// ── helpers internos (copy do EChartsCard, intencional — manter coesao
// editorial sem importar do EChartsCard publicamente) ────────────────────

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

function ChartError({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 py-8">
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

export {
  buildEditorialAreaOption,
  editorialChartColors,
  type EditorialAreaOptions,
  type EditorialAreaSeries,
} from "./buildEditorialOption"
